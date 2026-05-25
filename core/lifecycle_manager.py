"""
Lifecycle simulation layer for runtime validation.

This module does not touch UI directly. It models Android-like lifecycle and
network transitions, persists a serialized AppState snapshot, and emits events
for every state transition.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import logging
import threading
import time
from typing import Any, Dict, Optional

from . import app_state
from .event_bus import emit_threadsafe

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@dataclass
class LifecycleState:
    paused: bool = False
    background: bool = False
    network_connected: bool = True
    last_transition: Optional[str] = None
    last_changed_at: float = 0.0
    persisted_app_state: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_state = LifecycleState()
_lock = threading.RLock()


def get_state() -> LifecycleState:
    with _lock:
        return _state


def _capture_app_state() -> Dict[str, Any]:
    current = app_state.get_state().to_dict()
    # Copy into plain serializable containers to model persistence boundary.
    snapshot = {
        "current_book": dict(current["current_book"]) if current.get("current_book") else None,
        "current_chapter": dict(current["current_chapter"]) if current.get("current_chapter") else None,
        "active_downloads": list(current.get("active_downloads", [])),
        "crawler_status": dict(current.get("crawler_status", {})),
        "reading_theme": current.get("reading_theme"),
        "font_size": current.get("font_size"),
    }
    return snapshot


def _emit(event: str, reason: str) -> Dict[str, Any]:
    payload = {
        "state": get_state().to_dict(),
        "reason": reason,
        "timestamp": time.time(),
    }
    logger.info("Lifecycle event=%s reason=%s state=%s", event, reason, payload["state"])
    emit_threadsafe(event, payload)
    emit_threadsafe("lifecycle.changed", {"event": event, **payload})
    return payload


def _set_transition(name: str, *, paused: Optional[bool] = None, background: Optional[bool] = None, network_connected: Optional[bool] = None, persist_state: bool = False) -> Dict[str, Any]:
    with _lock:
        if paused is not None:
            _state.paused = paused
        if background is not None:
            _state.background = background
        if network_connected is not None:
            _state.network_connected = network_connected
        if persist_state:
            _state.persisted_app_state = _capture_app_state()
        _state.last_transition = name
        _state.last_changed_at = time.time()
    return _emit(f"lifecycle.{name}", name)


def simulate_pause() -> Dict[str, Any]:
    return _set_transition("pause", paused=True, persist_state=True)


def simulate_resume() -> Dict[str, Any]:
    payload = _set_transition("resume", paused=False)
    snapshot = get_persisted_app_state()
    emit_threadsafe(
        "lifecycle.restore",
        {
            "state": get_state().to_dict(),
            "restored_app_state": snapshot,
            "reason": "resume",
            "timestamp": time.time(),
        },
    )
    logger.info("Lifecycle restore emitted on resume; snapshot_exists=%s", bool(snapshot))
    return payload


def simulate_background() -> Dict[str, Any]:
    return _set_transition("background", background=True, persist_state=True)


def simulate_foreground() -> Dict[str, Any]:
    payload = _set_transition("foreground", background=False)
    snapshot = get_persisted_app_state()
    emit_threadsafe(
        "lifecycle.restore",
        {
            "state": get_state().to_dict(),
            "restored_app_state": snapshot,
            "reason": "foreground",
            "timestamp": time.time(),
        },
    )
    logger.info("Lifecycle restore emitted on foreground; snapshot_exists=%s", bool(snapshot))
    return payload


def simulate_network_disconnect() -> Dict[str, Any]:
    return _set_transition("network_disconnect", network_connected=False)


def simulate_network_restore() -> Dict[str, Any]:
    return _set_transition("network_restore", network_connected=True)


def get_persisted_app_state() -> Optional[Dict[str, Any]]:
    with _lock:
        if _state.persisted_app_state is None:
            return None
        return {
            "current_book": dict(_state.persisted_app_state["current_book"]) if _state.persisted_app_state.get("current_book") else None,
            "current_chapter": dict(_state.persisted_app_state["current_chapter"]) if _state.persisted_app_state.get("current_chapter") else None,
            "active_downloads": list(_state.persisted_app_state.get("active_downloads", [])),
            "crawler_status": dict(_state.persisted_app_state.get("crawler_status", {})),
            "reading_theme": _state.persisted_app_state.get("reading_theme"),
            "font_size": _state.persisted_app_state.get("font_size"),
        }
