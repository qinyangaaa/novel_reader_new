"""
Cold restore simulation for runtime validation.

This module simulates a process-killed rebuild without restarting the app.
It snapshots serializable runtime state, destroys in-memory runtime bindings,
restores them through provided callbacks, and returns PASS/FAIL validation data.
"""
from __future__ import annotations

import logging
import time
from copy import deepcopy
from typing import Any, Callable, Dict, Optional

from . import app_state, event_bus, lifecycle_manager, runtime_healthcheck
from .debug_tools import dump_eventbus_state, dump_screen_state, dump_task_state
from .event_bus import emit_threadsafe

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def _copy_dict(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    return deepcopy(data)


def _set_app_state(snapshot: Dict[str, Any]) -> None:
    with app_state._lock:
        app_state._state.current_book = _copy_dict(snapshot.get("current_book"))
        app_state._state.current_chapter = _copy_dict(snapshot.get("current_chapter"))
        app_state._state.active_downloads = list(snapshot.get("active_downloads", []))
        app_state._state.crawler_status = deepcopy(snapshot.get("crawler_status", {}))
        app_state._state.reading_theme = snapshot.get("reading_theme", "light")
        app_state._state.font_size = int(snapshot.get("font_size", 16))


def _set_lifecycle_state(snapshot: Dict[str, Any]) -> None:
    with lifecycle_manager._lock:
        lifecycle_manager._state.paused = bool(snapshot.get("paused", False))
        lifecycle_manager._state.background = bool(snapshot.get("background", False))
        lifecycle_manager._state.network_connected = bool(snapshot.get("network_connected", True))
        lifecycle_manager._state.last_transition = snapshot.get("last_transition")
        lifecycle_manager._state.last_changed_at = snapshot.get("last_changed_at", time.time())
        lifecycle_manager._state.persisted_app_state = _copy_dict(snapshot.get("persisted_app_state"))


def snapshot_runtime(download_manager: Optional[object] = None, screen_manager: Optional[object] = None) -> Dict[str, Any]:
    snapshot = {
        "created_at": time.time(),
        "app_state": _copy_dict(app_state.get_state().to_dict()),
        "lifecycle_state": _copy_dict(lifecycle_manager.get_state().to_dict()),
        "eventbus": dump_eventbus_state(),
        "screen_state": dump_screen_state(screen_manager),
        "current_screen": getattr(screen_manager, "current", None) if screen_manager is not None else None,
        "download_state": dump_task_state(download_manager),
    }
    logger.info(
        "Cold restore snapshot created current_screen=%s listeners=%s tasks=%s",
        snapshot["current_screen"],
        snapshot.get("eventbus", {}).get("total"),
        snapshot.get("download_state", {}).get("task_count"),
    )
    emit_threadsafe("cold_restore.snapshot", snapshot)
    return snapshot


def destroy_runtime(
    *,
    before_destroy: Optional[Callable[[], None]] = None,
    reset_download_manager: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    emit_threadsafe("cold_restore.destroying", {"timestamp": time.time()})
    if before_destroy:
        before_destroy()
    with event_bus._lock:
        event_bus._listeners.clear()
    with app_state._lock:
        app_state._state.current_book = None
        app_state._state.current_chapter = None
        app_state._state.active_downloads = []
        app_state._state.crawler_status = {}
        app_state._state.reading_theme = "light"
        app_state._state.font_size = 16
    with lifecycle_manager._lock:
        lifecycle_manager._state.paused = False
        lifecycle_manager._state.background = False
        lifecycle_manager._state.network_connected = True
        lifecycle_manager._state.last_transition = "destroyed"
        lifecycle_manager._state.last_changed_at = time.time()
    if reset_download_manager:
        reset_download_manager()
    summary = {
        "destroyed_at": time.time(),
        "listeners": 0,
        "app_state_reset": True,
    }
    logger.info("Cold restore destroy complete summary=%s", summary)
    return summary


def restore_runtime(
    snapshot: Dict[str, Any],
    *,
    rebuild_runtime: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    restore_download_manager: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    _set_app_state(snapshot.get("app_state", {}))
    _set_lifecycle_state(snapshot.get("lifecycle_state", {}))
    rebuild_info = rebuild_runtime(snapshot) if rebuild_runtime else {}
    restored_dm = restore_download_manager(snapshot.get("download_state", {})) if restore_download_manager else None
    payload = {
        "timestamp": time.time(),
        "current_screen": snapshot.get("current_screen"),
        "app_state": _copy_dict(app_state.get_state().to_dict()),
        "lifecycle_state": _copy_dict(lifecycle_manager.get_state().to_dict()),
    }
    logger.info(
        "Cold restore restored current_screen=%s rebuild_info=%s restored_dm=%s",
        payload["current_screen"],
        rebuild_info,
        restored_dm is not None,
    )
    emit_threadsafe("cold_restore.restored", payload)
    emit_threadsafe("cold_restore.rebound", {"timestamp": time.time(), "rebuild_info": rebuild_info})
    return {
        "payload": payload,
        "rebuild_info": rebuild_info,
        "download_manager_restored": restored_dm is not None,
    }


def validate_restore(
    snapshot: Dict[str, Any],
    *,
    screen_manager: Optional[object] = None,
    download_manager: Optional[object] = None,
    listener_baseline: Optional[Dict[str, Any]] = None,
    probe_seen: int = 0,
) -> Dict[str, Any]:
    expected_state = snapshot.get("app_state", {})
    listener_result = runtime_healthcheck.check_listener_leak(listener_baseline, tolerance=2)
    screen_result = runtime_healthcheck.check_screen_state(screen_manager)
    app_state_result = runtime_healthcheck.check_app_state_consistency(expected_state)
    task_result = runtime_healthcheck.check_task_backlog(download_manager, max_queue_size=8, max_pending_tasks=8)
    current_screen = getattr(screen_manager, "current", None) if screen_manager is not None else None
    screen_restore_ok = current_screen == snapshot.get("current_screen")
    eventbus_total = event_bus._listeners and sum(len(v) for v in event_bus._listeners.values()) or 0
    eventbus_ok = eventbus_total > 0 and probe_seen > 0
    download_state = snapshot.get("download_state", {})
    restored_task_count = task_result.get("extra", {}).get("summary", {}).get("task_count", 0)
    download_restore_ok = restored_task_count == download_state.get("task_count", 0)

    results = {
        "listener_rebind": {
            "name": "listener_rebind",
            "ok": listener_result["ok"] and eventbus_ok,
            "status": "PASS" if listener_result["ok"] and eventbus_ok else "FAIL",
            "detail": f"{listener_result['detail']}, eventbus_total={eventbus_total}, probe_seen={probe_seen}",
        },
        "screen_restore": {
            "name": "screen_restore",
            "ok": screen_result["ok"] and screen_restore_ok,
            "status": "PASS" if screen_result["ok"] and screen_restore_ok else "FAIL",
            "detail": f"{screen_result['detail']}, expected_current={snapshot.get('current_screen')}",
        },
        "app_state_recovery": {
            "name": "app_state_recovery",
            "ok": app_state_result["ok"],
            "status": app_state_result["status"],
            "detail": app_state_result["detail"],
        },
        "download_restore": {
            "name": "download_restore",
            "ok": task_result["ok"] and download_restore_ok,
            "status": "PASS" if task_result["ok"] and download_restore_ok else "FAIL",
            "detail": f"{task_result['detail']}, restored_task_count={restored_task_count}",
        },
        "eventbus_recovery": {
            "name": "eventbus_recovery",
            "ok": eventbus_ok,
            "status": "PASS" if eventbus_ok else "FAIL",
            "detail": f"eventbus_total={eventbus_total}, probe_seen={probe_seen}",
        },
    }
    overall_ok = all(item["ok"] for item in results.values())
    summary = {
        "name": "cold_restore",
        "ok": overall_ok,
        "status": "PASS" if overall_ok else "FAIL",
        "detail": "; ".join(f"{name}={item['status']}" for name, item in results.items()),
        "results": results,
    }
    logger.info("Cold restore validation -> %s | %s", summary["status"], summary["detail"])
    emit_threadsafe("cold_restore.validated", summary)
    return summary
