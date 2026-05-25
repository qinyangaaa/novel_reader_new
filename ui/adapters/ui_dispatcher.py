"""
UI 线程分发器：封装 Kivy Clock 调度，确保所有 UI 回调在主线程执行。
"""
from __future__ import annotations

from typing import Callable, Any

try:
    from kivy.clock import Clock
except Exception:
    # 在非 Kivy 环境下提供降级实现（立即调用），便于测试
    class Clock:
        @staticmethod
        def schedule_once(fn, timeout=0):
            fn(0)

from concurrent.futures import ThreadPoolExecutor
_bg_executor = ThreadPoolExecutor(max_workers=4)


def run_on_ui_thread(fn: Callable[[Any], None]) -> None:
    """把可调用对象安排到 UI 线程执行（使用 Kivy Clock）。

    fn 将接收一个参数 dt（与 Clock.schedule_once 兼容）。
    """
    Clock.schedule_once(fn, 0)


def dispatch_to_screen(screen: object, method_name: str, *args, **kwargs) -> None:
    """在 UI 线程上调用 screen 的指定方法（如果存在）。"""
    def _runner(dt):
        if screen is None:
            return
        fn = getattr(screen, method_name, None)
        if callable(fn):
            try:
                fn(*args, **kwargs)
            except Exception:
                pass

    run_on_ui_thread(_runner)


def safe_refresh(screen: object) -> None:
    """触发屏幕的安全刷新（调用 refresh 或 on_refresh 方法）。"""
    if hasattr(screen, "refresh"):
        dispatch_to_screen(screen, "refresh")
    elif hasattr(screen, "on_refresh"):
        dispatch_to_screen(screen, "on_refresh")


def run_in_background(fn, on_done=None):
    """在线程池中运行 fn()，当完成后在 UI 线程调用 on_done(result).

    fn: 无参函数，返回结果； on_done(result) 在 UI 线程执行。
    """
    def _worker():
        try:
            return fn()
        except Exception as e:
            return e

    future = _bg_executor.submit(_worker)

    def _callback(fut):
        res = None
        try:
            res = fut.result()
        except Exception as e:
            res = e

        if on_done:
            def _call(dt):
                try:
                    on_done(res)
                except Exception:
                    pass
            run_on_ui_thread(_call)

    future.add_done_callback(_callback)
    return future
