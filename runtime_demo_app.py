"""
Runtime validation app for the current Novel Reader architecture.

This is intentionally a diagnostic Kivy app, not the product UI. It validates:
- Screen lifecycle bind/unbind behavior
- Event storm dispatch through EventBus -> UI adapter -> Kivy main thread
- Weak listener cleanup
- AppState synchronization
- DownloadManager event flow with crawler fallback failure
"""
from __future__ import annotations

import gc
import logging
import os
import threading
import time
import weakref
from collections import OrderedDict
from functools import partial
from pathlib import Path

os.environ.setdefault("KIVY_HOME", str(Path(__file__).resolve().parent / ".kivy"))

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager
from kivy.uix.scrollview import ScrollView

from novel_reader.core import app_state, cold_restore, event_bus
from novel_reader.core.debug_tools import (
    dump_eventbus_state,
    dump_screen_state,
    dump_task_state,
    force_gc_and_check,
)
from novel_reader.core import lifecycle_manager, runtime_healthcheck
from novel_reader.ui.adapters import event_adapter
from novel_reader.ui.screens.bookshelf_screen import BookshelfScreen
from novel_reader.ui.screens.base_screen import BaseScreen

try:
    from novel_reader.ui.screens.search_screen import SearchScreen
    SEARCH_SCREEN_IMPORT_ERROR = None
except Exception as exc:
    SearchScreen = None
    SEARCH_SCREEN_IMPORT_ERROR = exc


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class ProbeScreen(BaseScreen):
    """Small runtime probe screen that records state and storm events."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app_state_updates = 0
        self.download_updates = 0
        self.storm_events = 0

        root = BoxLayout(orientation="vertical", padding=8, spacing=6)
        self.title = Label(text="Probe Screen", size_hint_y=None, height="32dp")
        self.state_label = Label(text="AppState updates: 0", size_hint_y=None, height="32dp")
        self.download_label = Label(text="Download updates: 0", size_hint_y=None, height="32dp")
        self.storm_label = Label(text="Storm events: 0", size_hint_y=None, height="32dp")
        self.lifecycle_label = Label(text="Lifecycle: idle", size_hint_y=None, height="32dp")
        root.add_widget(self.title)
        root.add_widget(self.state_label)
        root.add_widget(self.download_label)
        root.add_widget(self.storm_label)
        root.add_widget(self.lifecycle_label)
        self.add_widget(root)

    def on_enter(self, *args):
        super().on_enter(*args)
        event_adapter.bind_event("runtime.storm", self.on_storm_event, screen=self, weak=True)
        event_adapter.bind_event("download.failed", self.on_download_event, screen=self, weak=True)
        event_adapter.bind_event("download.completed", self.on_download_event, screen=self, weak=True)
        event_adapter.bind_event("lifecycle.changed", self.on_lifecycle_event, screen=self, weak=True)
        event_adapter.bind_event("lifecycle.restore", self.on_restore_event, screen=self, weak=True)

    def on_app_state(self, state):
        self.app_state_updates += 1
        book = state.get("current_book") if isinstance(state, dict) else None
        title = (book or {}).get("title", "None") if isinstance(book, dict) else str(book)
        self.state_label.text = f"AppState updates: {self.app_state_updates} | current_book={title}"

    def on_downloads(self, state):
        self.download_updates += 1
        active = state.get("active_downloads", state) if isinstance(state, dict) else state
        self.download_label.text = f"Download updates: {self.download_updates} | active={len(active or [])}"

    def on_storm_event(self, payload):
        self.storm_events += 1
        if self.storm_events % 50 == 0 or payload.get("index") == payload.get("total") - 1:
            self.storm_label.text = f"Storm events: {self.storm_events}"

    def on_download_event(self, payload):
        task = payload.get("task", {})
        self.download_label.text = f"Download event: {task.get('status')} {task.get('id', '')[:8]}"

    def on_lifecycle_event(self, payload):
        event_name = payload.get("event", "lifecycle.unknown")
        state = payload.get("state", {})
        self.lifecycle_label.text = (
            f"Lifecycle: {event_name.split('.')[-1]} "
            f"bg={state.get('background')} pause={state.get('paused')}"
        )

    def on_restore_event(self, payload):
        restored = payload.get("restored_app_state") or {}
        title = ((restored.get("current_book") or {}).get("title")) if isinstance(restored, dict) else None
        self.lifecycle_label.text = f"Restore: {payload.get('reason')} book={title or 'None'}"


class MissingDependencyScreen(BaseScreen):
    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=8, spacing=6)
        root.add_widget(Label(text="Screen unavailable", size_hint_y=None, height="32dp"))
        root.add_widget(Label(text=message))
        self.add_widget(root)


class RuntimeDemoApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.download_manager = None
        self.download_manager_error = None
        self.lifecycle_running = False
        self.storm_running = False
        self.storm_received = 0
        self.weak_probe_ref = None
        self.validation_results = OrderedDict()
        self._storm_expected = 0
        self._lifecycle_baseline = {}
        self._listener_baseline = {}
        self._last_persisted_state = None
        self._restore_events_seen = 0
        self._lifecycle_probe_seen = 0
        self._cold_restore_snapshot = None
        self._cold_restore_probe_seen = 0
        self._cold_restore_rebuilds = 0
        self._runtime_tokens = []
        self.root_layout = None

    def build(self):
        self.title = "Novel Reader Runtime Demo"

        root = BoxLayout(orientation="vertical", padding=8, spacing=8)
        self.root_layout = root
        controls_root = BoxLayout(orientation="vertical", size_hint_y=None, height="144dp", spacing=6)
        root.add_widget(controls_root)
        controls = BoxLayout(spacing=6)
        lifecycle_controls = BoxLayout(spacing=6)
        restore_controls = BoxLayout(spacing=6)
        controls_root.add_widget(controls)
        controls_root.add_widget(lifecycle_controls)
        controls_root.add_widget(restore_controls)

        self.manager = ScreenManager()
        self._populate_screen_manager(self.manager)
        root.add_widget(self.manager)

        diagnostics = BoxLayout(orientation="horizontal", size_hint_y=0.35, spacing=8)
        root.add_widget(diagnostics)

        self.result_label = Label(text="validations:\n- pending", valign="top", halign="left")
        self.result_label.bind(size=self._sync_result_text)
        diagnostics.add_widget(self.result_label)

        self.log_label = Label(text="", size_hint_y=None, valign="top", halign="left")
        self.log_label.bind(texture_size=self._resize_log_label)
        self.log_label.bind(size=self._sync_log_text)
        scroll = ScrollView()
        scroll.add_widget(self.log_label)
        diagnostics.add_widget(scroll)

        buttons = [
            ("Probe", partial(self.switch_screen, "probe")),
            ("Bookshelf", partial(self.switch_screen, "bookshelf")),
            ("Search", partial(self.switch_screen, "search")),
            ("AppState", self.validate_app_state),
            ("Storm", self.run_event_storm),
            ("Lifecycle", self.run_lifecycle_test),
            ("Weak GC", self.run_weak_listener_test),
            ("Download", self.run_download_test),
            ("All", self.run_all_validations),
            ("Dump", self.dump_runtime_state),
        ]
        for text, callback in buttons:
            btn = Button(text=text)
            btn.bind(on_press=lambda _btn, cb=callback: cb())
            controls.add_widget(btn)

        lifecycle_buttons = [
            ("Pause", self.simulate_pause),
            ("Resume", self.simulate_resume),
            ("BG", self.simulate_background),
            ("FG", self.simulate_foreground),
            ("Net Off", self.simulate_network_disconnect),
            ("Net On", self.simulate_network_restore),
            ("Lifecycle Auto", self.run_lifecycle_recovery_test),
        ]
        for text, callback in lifecycle_buttons:
            btn = Button(text=text)
            btn.bind(on_press=lambda _btn, cb=callback: cb())
            lifecycle_controls.add_widget(btn)

        restore_buttons = [
            ("Cold Restore Test", self.run_cold_restore_test),
            ("Full Runtime Rebuild", self.run_full_runtime_rebuild),
        ]
        for text, callback in restore_buttons:
            btn = Button(text=text)
            btn.bind(on_press=lambda _btn, cb=callback: cb())
            restore_controls.add_widget(btn)

        self.bind_runtime_listeners()

        Clock.schedule_once(lambda _dt: self.dump_runtime_state(), 0.2)
        return root

    def _populate_screen_manager(self, manager: ScreenManager):
        manager.add_widget(BookshelfScreen(name="bookshelf"))
        if SearchScreen is None:
            manager.add_widget(MissingDependencyScreen(str(SEARCH_SCREEN_IMPORT_ERROR), name="search"))
        else:
            manager.add_widget(SearchScreen(name="search"))
        manager.add_widget(ProbeScreen(name="probe"))

    def _build_screen_manager(self, current: str | None = None) -> ScreenManager:
        manager = ScreenManager()
        self._populate_screen_manager(manager)
        if current and current in [screen.name for screen in manager.screens]:
            manager.current = current
        return manager

    def _replace_screen_manager(self, current: str | None = None):
        new_manager = self._build_screen_manager(current)
        if self.root_layout is not None and self.manager is not None:
            self.root_layout.remove_widget(self.manager)
            self.root_layout.add_widget(new_manager, index=1)
        self.manager = new_manager
        self.log(f"screen manager rebuilt current={self.manager.current}")

    def clear_runtime_listeners(self):
        for token in list(self._runtime_tokens):
            event_adapter.unbind_event(token)
        self._runtime_tokens = []

    def bind_runtime_listeners(self):
        self.clear_runtime_listeners()
        self._runtime_tokens.extend(
            [
                event_adapter.bind_event("runtime.storm", self._on_storm_seen, weak=True),
                event_adapter.bind_event("download.created", self._on_download_seen, weak=True),
                event_adapter.bind_event("download.updated", self._on_download_seen, weak=True),
                event_adapter.bind_event("download.failed", self._on_download_seen, weak=True),
                event_adapter.bind_event("download.completed", self._on_download_seen, weak=True),
                event_adapter.bind_event("lifecycle.changed", self._on_lifecycle_changed, weak=True),
                event_adapter.bind_event("lifecycle.restore", self._on_lifecycle_restore, weak=True),
                event_adapter.bind_event("runtime.lifecycle_probe", self._on_lifecycle_probe_seen, weak=True),
                event_adapter.bind_event("cold_restore.restored", self._on_cold_restore_event, weak=True),
                event_adapter.bind_event("cold_restore.rebound", self._on_cold_restore_event, weak=True),
                event_adapter.bind_event("cold_restore.validated", self._on_cold_restore_event, weak=True),
            ]
        )
        self._runtime_tokens.append(
            event_bus.subscribe("runtime.cold_restore_probe", self._on_cold_restore_probe_direct, weak=False)
        )

    def _resize_log_label(self, *_args):
        self.log_label.height = max(self.log_label.texture_size[1], 120)

    def _sync_log_text(self, *_args):
        self.log_label.text_size = (self.log_label.width, None)

    def _sync_result_text(self, *_args):
        self.result_label.text_size = (self.result_label.width, None)

    def log(self, message: str):
        stamp = time.strftime("%H:%M:%S")
        lines = (self.log_label.text.splitlines() + [f"{stamp} {message}"])[-18:]
        self.log_label.text = "\n".join(lines)
        logger.info(message)

    def record_validation(self, name: str, ok: bool, detail: str):
        status = "PASS" if ok else "FAIL"
        self.validation_results[name] = f"{status} {name}: {detail}"
        self.result_label.text = "validations:\n" + "\n".join(self.validation_results.values())
        self.log(f"{name} -> {status.lower()} | {detail}")

    def record_healthcheck(self, result: dict):
        self.record_validation(result["name"], result["ok"], result["detail"])

    def switch_screen(self, name: str, *_args):
        self.manager.current = name
        self.log(f"screen -> {name}")

    def validate_app_state(self, *_args):
        idx = int(time.time() * 1000) % 100000
        app_state.update_current_book({"id": idx, "title": f"Runtime Book {idx}"})
        app_state.set_font_size(14 + idx % 8)
        result = runtime_healthcheck.check_app_state_consistency(app_state.get_state().to_dict())
        self.record_validation("app_state", result["ok"], f"current_book={idx}; {result['detail']}")

    def run_event_storm(self, *_args):
        if self.storm_running:
            self.log("event storm already running")
            return
        self.storm_running = True
        self.storm_received = 0
        total = 500
        self._storm_expected = total

        def worker():
            started = time.time()
            for index in range(total):
                event_bus.emit_threadsafe("runtime.storm", {"index": index, "total": total})
            elapsed = time.time() - started
            Clock.schedule_once(lambda _dt: self._finish_storm(elapsed, 0), 0.2)

        threading.Thread(target=worker, daemon=True).start()
        self.log(f"event storm started: {total}")

    def _finish_storm(self, elapsed: float, retries: int):
        total = self._storm_expected
        if self.storm_received < total and retries < 10:
            Clock.schedule_once(lambda _dt: self._finish_storm(elapsed, retries + 1), 0.2)
            return
        self.storm_running = False
        self.record_healthcheck(runtime_healthcheck.check_event_storm(total, self.storm_received, elapsed))
        self.dump_runtime_state()

    def _on_storm_seen(self, payload):
        self.storm_received += 1

    def run_lifecycle_test(self, *_args):
        if self.lifecycle_running:
            self.log("lifecycle test already running")
            return
        self.lifecycle_running = True
        sequence = ["bookshelf", "search", "probe"] * 20
        self._lifecycle_baseline = dump_eventbus_state()
        self._listener_baseline = self._lifecycle_baseline
        self.log(f"lifecycle test started: {len(sequence)} switches")

        def step(index: int, _dt=0):
            if index >= len(sequence):
                self.lifecycle_running = False
                gc.collect()
                self._finish_lifecycle_test(len(sequence))
                self.dump_runtime_state()
                return
            self.manager.current = sequence[index]
            Clock.schedule_once(partial(step, index + 1), 0.03)

        step(0)

    def _finish_lifecycle_test(self, total_switches: int):
        listener_result = runtime_healthcheck.check_listener_leak(self._lifecycle_baseline, tolerance=1)
        screen_result = runtime_healthcheck.check_screen_state(self.manager)
        self.record_validation("screen_lifecycle", listener_result["ok"] and screen_result["ok"], f"switches={total_switches}; {listener_result['detail']} | {screen_result['detail']}")

    def run_weak_listener_test(self, *_args):
        class TempListener:
            def __init__(self):
                self.called = 0

            def handle(self, payload):
                self.called += 1

        probe = TempListener()
        token = event_bus.subscribe("runtime.weak_probe", probe.handle, weak=True)
        event_bus.emit("runtime.weak_probe", {"phase": "alive"})
        self.weak_probe_ref = weakref.ref(probe)
        del probe
        result = force_gc_and_check("runtime.weak_probe")
        alive = self.weak_probe_ref() is not None
        still_registered = token in result["listeners"].get("runtime.weak_probe", {})
        self.record_validation(
            "weak_listener",
            (not alive) and (not still_registered),
            f"alive={alive}, still_registered={still_registered}",
        )

    def run_download_test(self, *_args):
        if self.download_manager is None and self.download_manager_error is None:
            try:
                from novel_reader.services.download_manager import DownloadManager

                self.download_manager = DownloadManager(max_workers=2)
            except Exception as exc:
                self.download_manager_error = exc

        if self.download_manager is None:
            self.record_validation("download_flow", False, f"unavailable: {self.download_manager_error}")
            return

        task_id = self.download_manager.queue_download("https://runtime.invalid/chapter/1")
        self.log(f"download queued: {task_id[:8]}")
        Clock.schedule_once(lambda _dt: self._check_download_result(task_id, 0), 0.3)

    def _on_download_seen(self, payload):
        task = payload.get("task", payload)
        self.log(f"download event: {task.get('status')} {task.get('id', '')[:8]}")

    def _check_download_result(self, task_id: str, retries: int):
        if self.download_manager is None:
            return
        task_meta = self.download_manager.get_task(task_id)
        if not task_meta:
            self.record_validation("download_flow", False, "task disappeared")
            return
        task = task_meta.get("task", {})
        status = task.get("status")
        if status in ("pending", "running") and retries < 20:
            Clock.schedule_once(lambda _dt: self._check_download_result(task_id, retries + 1), 0.2)
            return
        ok = status in ("completed", "failed")
        backlog_result = runtime_healthcheck.check_task_backlog(self.download_manager)
        self.record_validation("download_flow", ok and backlog_result["ok"], f"status={status}; {backlog_result['detail']}")

    def simulate_pause(self, *_args):
        lifecycle_manager.simulate_pause()

    def simulate_resume(self, *_args):
        lifecycle_manager.simulate_resume()

    def simulate_background(self, *_args):
        lifecycle_manager.simulate_background()

    def simulate_foreground(self, *_args):
        lifecycle_manager.simulate_foreground()

    def simulate_network_disconnect(self, *_args):
        lifecycle_manager.simulate_network_disconnect()

    def simulate_network_restore(self, *_args):
        lifecycle_manager.simulate_network_restore()

    def _on_lifecycle_changed(self, payload):
        state = payload.get("state", {})
        event_name = payload.get("event", "lifecycle.unknown")
        self.log(
            f"{event_name} bg={state.get('background')} paused={state.get('paused')} "
            f"net={state.get('network_connected')}"
        )

    def _on_lifecycle_restore(self, payload):
        self._restore_events_seen += 1
        self._last_persisted_state = payload.get("restored_app_state")
        self.log(
            f"lifecycle.restore reason={payload.get('reason')} "
            f"snapshot={'yes' if self._last_persisted_state else 'no'}"
        )

    def _on_lifecycle_probe_seen(self, payload):
        self._lifecycle_probe_seen += 1

    def _on_cold_restore_event(self, payload):
        self.log(
            f"cold_restore event="
            f"{payload.get('name') or payload.get('rebuild_info') or payload.get('current_screen') or 'restore'}"
        )

    def _on_cold_restore_probe_seen(self, payload):
        self._cold_restore_probe_seen += 1

    def _on_cold_restore_probe_direct(self, payload):
        self._cold_restore_probe_seen += 1
        self.log(f"cold_restore_probe phase={payload.get('phase')}")

    def _reset_download_manager(self):
        self.download_manager = None
        self.download_manager_error = None

    def _ensure_download_manager(self):
        if self.download_manager is None and self.download_manager_error is None:
            try:
                from novel_reader.services.download_manager import DownloadManager

                self.download_manager = DownloadManager(max_workers=2)
            except Exception as exc:
                self.download_manager_error = exc
        return self.download_manager

    def _restore_download_manager(self, download_state: dict):
        manager = self._ensure_download_manager()
        if manager is None:
            return None
        tasks = download_state.get("tasks", {})
        from novel_reader.core.task_state import TaskInfo

        with manager.lock:
            manager.tasks = {}
            for task_id, task_data in tasks.items():
                task = TaskInfo(
                    id=task_data["id"],
                    url=task_data["url"],
                    status=task_data.get("status", "failed"),
                    retries=task_data.get("retries", 0),
                    result=task_data.get("result"),
                    created_at=task_data.get("created_at"),
                    updated_at=task_data.get("updated_at"),
                )
                manager.tasks[task_id] = {"id": task_id, "task": task, "future": None}
        self.log(f"download manager restored tasks={len(tasks)}")
        return manager

    def _rebuild_runtime(self, snapshot: dict):
        current = snapshot.get("current_screen") or "bookshelf"
        self._cold_restore_rebuilds += 1
        self._replace_screen_manager(current)
        self.bind_runtime_listeners()
        runtime_info = {"rebuilds": self._cold_restore_rebuilds, "current": current}
        self.log(f"runtime rebuilt rebuilds={self._cold_restore_rebuilds} current={current}")
        return runtime_info

    def _run_post_restore_probe(self):
        event_bus.emit_threadsafe("runtime.cold_restore_probe", {"phase": "post_restore"})
        event_bus.emit_threadsafe("app.current_book", {"current_book": app_state.get_state().current_book})
        event_bus.emit_threadsafe("app.active_downloads", {"active_downloads": list(app_state.get_state().active_downloads)})

    def run_full_runtime_rebuild(self, *_args):
        current = self.manager.current if self.manager is not None else "bookshelf"
        self._replace_screen_manager(current)
        self.bind_runtime_listeners()
        self.record_validation("full_runtime_rebuild", True, f"current={self.manager.current}")

    def run_lifecycle_recovery_test(self, *_args):
        self._listener_baseline = dump_eventbus_state()
        self._restore_events_seen = 0
        self._lifecycle_probe_seen = 0
        self._last_persisted_state = None
        self.validate_app_state()
        Clock.schedule_once(lambda _dt: self.simulate_background(), 0.05)
        Clock.schedule_once(lambda _dt: self.simulate_network_disconnect(), 0.10)
        Clock.schedule_once(lambda _dt: self.simulate_network_restore(), 0.20)
        Clock.schedule_once(lambda _dt: self.simulate_foreground(), 0.30)
        Clock.schedule_once(lambda _dt: self.simulate_pause(), 0.40)
        Clock.schedule_once(lambda _dt: self.simulate_resume(), 0.50)
        Clock.schedule_once(lambda _dt: event_bus.emit_threadsafe("runtime.lifecycle_probe", {"phase": "post_resume"}), 0.60)
        Clock.schedule_once(lambda _dt: self._finish_lifecycle_recovery_test(), 0.90)

    def _finish_lifecycle_recovery_test(self):
        listener_result = runtime_healthcheck.check_listener_leak(self._listener_baseline, tolerance=2)
        screen_result = runtime_healthcheck.check_screen_state(self.manager)
        app_state_result = runtime_healthcheck.check_app_state_consistency(self._last_persisted_state)
        restore_ok = self._restore_events_seen >= 2 and self._lifecycle_probe_seen >= 1
        self.record_validation(
            "listener_recovery",
            restore_ok and listener_result["ok"],
            f"restore_events={self._restore_events_seen} probe_seen={self._lifecycle_probe_seen}; {listener_result['detail']}",
        )
        self.record_healthcheck(screen_result)
        self.record_validation(
            "app_state_restore",
            app_state_result["ok"],
            app_state_result["detail"],
        )

    def run_cold_restore_test(self, *_args):
        self._ensure_download_manager()
        self._cold_restore_probe_seen = 0
        self._listener_baseline = dump_eventbus_state()
        self.validate_app_state()
        if self.download_manager is not None and not self.download_manager.list_tasks():
            self.run_download_test()
        Clock.schedule_once(lambda _dt: self._start_cold_restore_test(), 0.7)

    def _start_cold_restore_test(self):
        self._cold_restore_snapshot = cold_restore.snapshot_runtime(self.download_manager, self.manager)
        self.log(
            f"cold restore snapshot current={self._cold_restore_snapshot.get('current_screen')} "
            f"tasks={self._cold_restore_snapshot.get('download_state', {}).get('task_count', 0)}"
        )
        cold_restore.destroy_runtime(
            before_destroy=self.clear_runtime_listeners,
            reset_download_manager=self._reset_download_manager,
        )
        Clock.schedule_once(lambda _dt: self._finish_cold_restore_rebuild(), 0.2)

    def _finish_cold_restore_rebuild(self):
        if not self._cold_restore_snapshot:
            self.record_validation("cold_restore", False, "missing snapshot")
            return
        cold_restore.restore_runtime(
            self._cold_restore_snapshot,
            rebuild_runtime=self._rebuild_runtime,
            restore_download_manager=self._restore_download_manager,
        )
        Clock.schedule_once(lambda _dt: self._run_post_restore_probe(), 0.2)
        Clock.schedule_once(lambda _dt: self._validate_cold_restore(), 0.5)

    def _validate_cold_restore(self):
        if not self._cold_restore_snapshot:
            self.record_validation("cold_restore", False, "missing snapshot")
            return
        summary = cold_restore.validate_restore(
            self._cold_restore_snapshot,
            screen_manager=self.manager,
            download_manager=self.download_manager,
            listener_baseline=self._listener_baseline,
            probe_seen=self._cold_restore_probe_seen,
        )
        for name, item in summary["results"].items():
            self.record_validation(name, item["ok"], item["detail"])
        self.record_validation("cold_restore", summary["ok"], summary["detail"])

    def run_all_validations(self, *_args):
        self.validate_app_state()
        self.run_weak_listener_test()
        self.run_event_storm()
        Clock.schedule_once(lambda _dt: self.run_lifecycle_test(), 0.4)
        Clock.schedule_once(lambda _dt: self.run_download_test(), 0.8)
        Clock.schedule_once(lambda _dt: self.run_lifecycle_recovery_test(), 1.2)
        Clock.schedule_once(lambda _dt: self.run_cold_restore_test(), 2.3)

    def dump_runtime_state(self, *_args):
        eventbus = dump_eventbus_state()
        screens = dump_screen_state(self.manager)
        tasks = dump_task_state(self.download_manager)
        self.log(
            "dump: "
            f"listeners={eventbus.get('total')} "
            f"events={eventbus.get('events')} "
            f"screens={len(screens)} "
            f"tasks={tasks.get('task_count', 0)}"
        )


if __name__ == "__main__":
    RuntimeDemoApp().run()
