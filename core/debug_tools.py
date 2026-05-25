"""调试工具：用于导出 EventBus / listeners / tasks / screens 状态，帮助诊断泄漏与事件风暴。

说明：这些函数直接读取模块级私有变量以便在运行时观察内部状态。
仅用于调试环境（runtime_demo_app.py）。
"""
from __future__ import annotations

import logging
import types
import gc
from typing import Optional

from . import event_bus

logger = logging.getLogger(__name__)


def dump_eventbus_state() -> dict:
    """返回并打印 EventBus 当前的订阅摘要。"""
    try:
        listeners = getattr(event_bus, "_listeners", {})
    except Exception as e:
        logger.exception("无法访问 event_bus._listeners: %s", e)
        return {}

    summary = {}
    total = 0
    for event, m in listeners.items():
        count = len(m)
        weak_count = sum(1 for _, info in m.items() if info.get("weak"))
        strong_count = count - weak_count
        summary[event] = {"count": count, "weak": weak_count, "strong": strong_count}
        total += count

    logger.info("EventBus summary: total_listeners=%d events=%d details=%s", total, len(summary), summary)
    return {"total": total, "events": len(summary), "details": summary}


def dump_active_listeners(event: Optional[str] = None) -> dict:
    """列出指定事件或全部事件的 listener token、类型与存活状态。"""
    listeners = getattr(event_bus, "_listeners", {})
    out = {}
    for ev, m in listeners.items():
        if event and ev != event:
            continue
        ev_list = {}
        for token, info in m.items():
            is_weak = bool(info.get("weak"))
            alive = True
            ref_repr = None
            try:
                if is_weak:
                    ref = info.get("ref")
                    fn = ref() if ref is not None else None
                    alive = fn is not None
                    ref_repr = repr(fn)
                else:
                    ref_repr = repr(info.get("ref"))
            except Exception:
                alive = False
            ev_list[token] = {"weak": is_weak, "alive": alive, "repr": ref_repr}
        out[ev] = ev_list

    logger.info("Active listeners dump for event=%s: %s", event, {k: len(v) for k, v in out.items()})
    return out


def dump_task_state(dm: Optional[object] = None) -> dict:
    """尝试导出 DownloadManager（或任意类似对象）的任务列表与队列长度。

    dm: DownloadManager 实例，可选；如果为 None，仅返回空结构。
    """
    if dm is None:
        logger.info("No DownloadManager instance provided to dump_task_state")
        return {}

    try:
        tasks = getattr(dm, "tasks", {})
        executor = getattr(dm, "executor", None)
        qsize = None
        if executor is not None:
            try:
                q = getattr(executor, "_work_queue", None)
                if q is not None:
                    qsize = q.qsize()
            except Exception:
                qsize = None

        summary = {"task_count": len(tasks), "queue_size": qsize, "tasks": {k: (v.get("task").to_dict() if v.get("task") is not None else None) for k, v in tasks.items()}}
        logger.info("DownloadManager state: task_count=%d queue_size=%s", len(tasks), qsize)
        return summary
    except Exception as e:
        logger.exception("dump_task_state failed: %s", e)
        return {}


def dump_screen_state(screen_manager: Optional[object] = None) -> dict:
    """导出 ScreenManager 的屏幕和每个屏幕的绑定 token（若存在）。"""
    out = {}
    try:
        if screen_manager is None:
            logger.info("No ScreenManager provided to dump_screen_state")
            return {}

        for screen in list(screen_manager.screens):
            name = getattr(screen, "name", screen.__class__.__name__)
            tokens = getattr(screen, "_event_adapter_tokens", [])
            out[name] = {"tokens": list(tokens), "repr": repr(screen)}

        logger.info("ScreenManager state: screens=%d", len(out))
        return out
    except Exception as e:
        logger.exception("dump_screen_state failed: %s", e)
        return {}


def force_gc_and_check(event: Optional[str] = None) -> dict:
    """强制 GC 并返回 dump_eventbus_state 与 active_listeners（可用于检测弱引用释放）。"""
    gc.collect()
    return {"eventbus": dump_eventbus_state(), "listeners": dump_active_listeners(event)}
