"""
事件适配器：UI 层使用的安全封装，负责 subscribe/unsubscribe、弱引用监听、自动清理。

UI 层只调用此模块，不直接使用 core.event_bus。
"""
from __future__ import annotations

import weakref
from typing import Callable, Optional

from ...core import event_bus
from . import ui_dispatcher


def bind_event(event: str, handler: Callable[[dict], None], screen: Optional[object] = None, weak: bool = True) -> str:
    """绑定事件到 handler，并在事件触发时保证在 UI 线程调用。

    - `screen` 可选：若提供，token 会自动附加到 screen 上，便于生命周期清理。
    - `weak` 支持弱引用 handler（若 handler 为 bound method，则使用 WeakMethod）。
    返回订阅 token。
    """
    # 创建对原始 handler 的弱引用
    if weak:
        if hasattr(handler, "__self__") and handler.__self__ is not None:
            ref = weakref.WeakMethod(handler)
        else:
            try:
                ref = weakref.ref(handler)
            except TypeError:
                # 无法创建弱引用（例如内置函数），使用强引用
                ref = None
    else:
        ref = None

    def _listener(payload: dict):
        # 运行在事件线程；切换到 UI 线程
        def _call(dt):
            if ref is not None:
                fn = ref()
                if fn is None:
                    # 被回收，尽早取消订阅
                    try:
                        event_bus.unsubscribe(token)
                    except Exception:
                        pass
                    return
                fn(payload)
            else:
                # 强引用或无法弱引用的处理
                handler(payload)

        ui_dispatcher.run_on_ui_thread(_call)

    # 将 wrapper 注册到底层 event bus（使用强引用 wrapper）
    token = event_bus.subscribe(event, _listener, weak=False)

    # 将 token 记录在 screen 上，便于 auto_cleanup
    if screen is not None:
        try:
            lst = getattr(screen, "_event_adapter_tokens", None)
            if lst is None:
                lst = []
                setattr(screen, "_event_adapter_tokens", lst)
            lst.append(token)
        except Exception:
            pass

    return token


def unbind_event(token: str) -> bool:
    """取消订阅（按 token）。"""
    try:
        return event_bus.unsubscribe(token)
    except Exception:
        return False


def auto_cleanup(screen: object) -> None:
    """清理绑定到 screen 的所有 token（在 screen 销毁时调用）。"""
    try:
        lst = getattr(screen, "_event_adapter_tokens", None)
        if not lst:
            return
        for t in list(lst):
            try:
                event_bus.unsubscribe(t)
            except Exception:
                pass
        setattr(screen, "_event_adapter_tokens", [])
    except Exception:
        pass
