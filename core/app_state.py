"""
应用全局状态管理（线程安全），并通过 EventBus 广播变化。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any, List
import threading

from .event_bus import emit_threadsafe


@dataclass
class AppState:
    current_book: Optional[Dict[str, Any]] = None
    current_chapter: Optional[Dict[str, Any]] = None
    active_downloads: List[str] = field(default_factory=list)
    crawler_status: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    reading_theme: str = "light"
    font_size: int = 16

    def to_dict(self) -> dict:
        return asdict(self)


# 单例 app state
_state = AppState()
_lock = threading.RLock()


def get_state() -> AppState:
    with _lock:
        return _state


def update_current_book(book: Optional[Dict[str, Any]]) -> None:
    with _lock:
        _state.current_book = book
        emit_threadsafe("app.current_book", {"current_book": _state.current_book})


def update_current_chapter(chapter: Optional[Dict[str, Any]]) -> None:
    with _lock:
        _state.current_chapter = chapter
        emit_threadsafe("app.current_chapter", {"current_chapter": _state.current_chapter})


def add_active_download(task_id: str) -> None:
    with _lock:
        if task_id not in _state.active_downloads:
            _state.active_downloads.append(task_id)
            emit_threadsafe("app.active_downloads", {"active_downloads": list(_state.active_downloads)})


def remove_active_download(task_id: str) -> None:
    with _lock:
        if task_id in _state.active_downloads:
            _state.active_downloads.remove(task_id)
            emit_threadsafe("app.active_downloads", {"active_downloads": list(_state.active_downloads)})


def set_crawler_status(name: str, status: Dict[str, Any]) -> None:
    with _lock:
        _state.crawler_status[name] = status
        emit_threadsafe("app.crawler_status", {"name": name, "status": status})


def set_reading_theme(theme: str) -> None:
    with _lock:
        _state.reading_theme = theme
        emit_threadsafe("app.reading_theme", {"reading_theme": theme})


def set_font_size(size: int) -> None:
    with _lock:
        _state.font_size = int(size)
        emit_threadsafe("app.font_size", {"font_size": _state.font_size})
