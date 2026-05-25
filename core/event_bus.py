"""
线程安全事件总线，支持弱引用 listener，emit 与 emit_threadsafe。

接口：subscribe(event, listener, weak=True) -> token
       unsubscribe(token)
       emit(event, payload)
       emit_threadsafe(event, payload)
"""
from __future__ import annotations

import threading
import weakref
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

_lock = threading.RLock()
_listeners: Dict[str, Dict[str, Any]] = {}  # event -> token -> weakref
_executor = ThreadPoolExecutor(max_workers=4)


def _make_weak_ref(func: Callable, callback: Optional[Callable] = None):
    """返回适当的 weakref，对函数使用 ref，对 bound method 使用 WeakMethod。"""
    try:
        if hasattr(func, "__self__") and func.__self__ is not None:
            # bound method
            return weakref.WeakMethod(func, callback)
        else:
            return weakref.ref(func, callback)
    except Exception:
        return weakref.ref(func, callback)


def subscribe(event: str, listener: Callable[[Dict], None], weak: bool = True) -> str:
    """订阅事件，返回 token。listener(payload: dict)

    如果 weak=True，使用弱引用，监听对象被回收后自动注销。
    """
    token = uuid.uuid4().hex
    with _lock:
        if event not in _listeners:
            _listeners[event] = {}

        if weak:
            ref = _make_weak_ref(listener, lambda r: _remove_dead(event, token))
            _listeners[event][token] = {"ref": ref, "weak": True}
        else:
            _listeners[event][token] = {"ref": listener, "weak": False}
    return token


def _remove_dead(event: str, token: str) -> None:
    with _lock:
        if event in _listeners and token in _listeners[event]:
            del _listeners[event][token]


def unsubscribe(token: str) -> bool:
    """通过 token 取消订阅。"""
    with _lock:
        for event, m in list(_listeners.items()):
            if token in m:
                del m[token]
                return True
    return False


def emit(event: str, payload: Dict[str, Any]) -> None:
    """同步触发事件，按订阅顺序调用监听器。"""
    with _lock:
        entries = list(_listeners.get(event, {}).items())
    for token, info in entries:
        try:
            if info["weak"]:
                func = info["ref"]()
                if func is None:
                    # dead, remove
                    _remove_dead(event, token)
                    continue
            else:
                func = info["ref"]
            # call listener
            func(payload)
        except Exception:
            # listener exceptions should not stop propagation
            continue


def emit_threadsafe(event: str, payload: Dict[str, Any]) -> None:
    """在线程池中异步触发事件，确保调用方线程不会被阻塞。"""
    # 执行副本，避免闭包捕获可变 payload
    p = dict(payload)
    def _runner():
        try:
            emit(event, p)
        except Exception:
            pass

    _executor.submit(_runner)
