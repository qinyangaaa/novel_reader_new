"""
Runtime health checks for lifecycle and event-driven validation.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from . import app_state, lifecycle_manager
from .debug_tools import dump_eventbus_state, dump_screen_state, dump_task_state

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def _result(name: str, ok: bool, detail: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {"name": name, "ok": ok, "status": "PASS" if ok else "FAIL", "detail": detail}
    if extra:
        payload["extra"] = extra
    logger.info("Healthcheck %s -> %s | %s", name, payload["status"], detail)
    return payload


def check_listener_leak(baseline: Optional[Dict[str, Any]] = None, tolerance: int = 1) -> Dict[str, Any]:
    current = dump_eventbus_state()
    if baseline is None:
        return _result("listener_leak", True, f"baseline_only total={current.get('total', 0)}", {"current": current})

    base_total = baseline.get("total", 0)
    current_total = current.get("total", 0)
    delta = current_total - base_total
    ok = delta <= tolerance
    return _result(
        "listener_leak",
        ok,
        f"baseline={base_total}, current={current_total}, delta={delta}, tolerance={tolerance}",
        {"baseline": baseline, "current": current},
    )


def check_event_storm(expected: int, received: int, elapsed: Optional[float] = None) -> Dict[str, Any]:
    ok = expected == received
    detail = f"expected={expected}, received={received}"
    if elapsed is not None:
        detail += f", emit_time={elapsed:.3f}s"
    return _result("event_storm", ok, detail)


def check_task_backlog(download_manager: Optional[object], max_queue_size: int = 4, max_pending_tasks: int = 8) -> Dict[str, Any]:
    summary = dump_task_state(download_manager)
    queue_size = summary.get("queue_size")
    tasks = summary.get("tasks", {})
    pending = sum(1 for task in tasks.values() if task and task.get("status") in ("pending", "running"))
    queue_ok = queue_size is None or queue_size <= max_queue_size
    pending_ok = pending <= max_pending_tasks
    ok = queue_ok and pending_ok
    return _result(
        "task_backlog",
        ok,
        f"queue_size={queue_size}, pending={pending}, task_count={summary.get('task_count', 0)}",
        {"summary": summary},
    )


def check_screen_state(screen_manager: Optional[object]) -> Dict[str, Any]:
    screens = dump_screen_state(screen_manager)
    if not screen_manager or not screens:
        return _result("screen_state", False, "no_screens")

    current = getattr(screen_manager, "current", None)
    names = list(screens.keys())
    token_counts = {name: len(data.get("tokens", [])) for name, data in screens.items()}
    duplicate_risk = any(count > 6 for count in token_counts.values())
    ok = current in names and not duplicate_risk
    detail = f"current={current}, screens={len(names)}, tokens={token_counts}"
    return _result("screen_state", ok, detail, {"screens": screens})


def check_app_state_consistency(expected_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = app_state.get_state().to_dict()
    lifecycle = lifecycle_manager.get_state().to_dict()
    active_downloads = current.get("active_downloads", [])
    unique_downloads = len(active_downloads) == len(set(active_downloads))
    serializable_shape = isinstance(current.get("crawler_status"), dict) and isinstance(current.get("font_size"), int)
    snapshot_ok = True
    if expected_snapshot is not None:
        snapshot_ok = current == expected_snapshot
    elif lifecycle.get("persisted_app_state") is not None:
        snapshot_ok = current == lifecycle.get("persisted_app_state")

    ok = unique_downloads and serializable_shape and snapshot_ok
    detail = (
        f"unique_downloads={unique_downloads}, serializable_shape={serializable_shape}, "
        f"snapshot_match={snapshot_ok}"
    )
    return _result("app_state_consistency", ok, detail, {"current": current, "lifecycle": lifecycle})
