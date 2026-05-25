"""
屏幕与 AppState/下载状态绑定工具。

负责把 AppState 的变化以安全方式同步到 Screen（通过 ui_dispatcher）。
"""
from __future__ import annotations

import weakref
from typing import Optional

from ...core import app_state
from . import event_adapter, ui_dispatcher


def bind_screen(screen: object, sync_on_bind: bool = True) -> None:
    """绑定 screen：自动添加 app state 与下载状态的监听，并在 screen 上记录 tokens。

    要求 screen 提供以下可选方法以接收回调（在 UI 线程调用）：
      - on_app_state(state: dict)
      - on_downloads(state: dict)

    若 screen 被回收，绑定会自动清理（因为使用弱引用）。
    """
    # 订阅 app state 更新
    def _app_handler(payload: dict):
        # 运行在 UI 线程（event_adapter 已经安排）
        fn = getattr(screen, "on_app_state", None)
        if callable(fn):
            fn(payload.get("current_book") or app_state.get_state().to_dict())

    def _downloads_handler(payload: dict):
        fn = getattr(screen, "on_downloads", None)
        if callable(fn):
            fn(payload.get("active_downloads") or app_state.get_state().active_downloads)

    # Local closures are not otherwise strongly referenced after bind_screen()
    # returns, so keep them alive through the adapter token until screen cleanup.
    event_adapter.bind_event("app.current_book", _app_handler, screen=screen, weak=False)
    event_adapter.bind_event("app.active_downloads", _downloads_handler, screen=screen, weak=False)

    if sync_on_bind:
        # 立刻同步一次当前状态到 screen
        ui_dispatcher.dispatch_to_screen(screen, "on_app_state", app_state.get_state().to_dict())
        ui_dispatcher.dispatch_to_screen(screen, "on_downloads", {"active_downloads": list(app_state.get_state().active_downloads)})


def unbind_screen(screen: object) -> None:
    """解除屏幕上所有由本模块绑定的事件。"""
    event_adapter.auto_cleanup(screen)


def sync_app_state(screen: object) -> None:
    """主动同步当前 AppState 到 screen（在 UI 线程）。"""
    ui_dispatcher.dispatch_to_screen(screen, "on_app_state", app_state.get_state().to_dict())


def sync_download_state(screen: object) -> None:
    """主动同步下载状态到 screen（在 UI 线程）。"""
    ui_dispatcher.dispatch_to_screen(screen, "on_downloads", {"active_downloads": list(app_state.get_state().active_downloads)})
