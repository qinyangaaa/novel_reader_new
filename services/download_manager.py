"""
下载管理器：负责并发下载、预加载、任务队列、取消与重试。

注意：不直接操作数据库或 UI。所有下载通过 CrawlerService.fetch_chapter 完成。
"""
from __future__ import annotations

import concurrent.futures
import threading
import uuid
import time
import logging
from typing import Any, Callable, Dict, List, Optional

from .crawler_service import CrawlerService
from ..core.event_bus import emit_threadsafe
from ..core.task_state import TaskInfo

from ..core.app_state import add_active_download, remove_active_download

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class DownloadManager:
    """管理下载任务与状态跟踪。

    任务元数据格式：
    { 'id', 'url', 'status', 'retries', 'future', 'result', 'created_at' }
    status in ('pending','running','completed','failed','cancelled')
    """

    def __init__(self, max_workers: int = 4):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.tasks: Dict[str, Dict] = {}
        self.lock = threading.RLock()

    def _submit(self, url: str, callback: Optional[Callable] = None, max_retries: int = 2) -> str:
        task_id = uuid.uuid4().hex
        task = TaskInfo(id=task_id, url=url)
        meta = {"id": task_id, "task": task, "future": None}
        with self.lock:
            self.tasks[task_id] = meta
        # emit created
        emit_threadsafe("download.created", task.to_dict())
        add_active_download(task_id)

        def _work():
            # running
            with self.lock:
                task.update_status("running")
            emit_threadsafe("download.updated", task.to_dict())
            try:
                # 使用 CrawlerService 进行抓取（包含 fallback）
                res = CrawlerService.fetch_chapter(url, per_crawler_retries=1)
                with self.lock:
                    task.update_status("completed" if res.get("ok") else "failed", result=res)
                if res.get("ok"):
                    emit_threadsafe("download.completed", {"task": task.to_dict(), "result": res})
                else:
                    emit_threadsafe("download.failed", {"task": task.to_dict(), "result": res})
            except Exception as e:
                logger.exception("下载任务异常: %s", e)
                with self.lock:
                    task.update_status("failed", result={"ok": False, "error": str(e)})
                emit_threadsafe("download.failed", {"task": task.to_dict(), "result": {"ok": False, "error": str(e)}})
            finally:
                if callback:
                    try:
                        callback(task.to_dict())
                    except Exception:
                        logger.exception("下载回调异常")
                # remove from active downloads
                remove_active_download(task.id)
            return task.to_dict()

        future = self.executor.submit(_work)
        with self.lock:
            meta["future"] = future

        # 添加完成回调以更新状态（当 future 已完成时）
        def _done(fut: concurrent.futures.Future):
            try:
                fut.result()
            except concurrent.futures.CancelledError:
                with self.lock:
                    task.update_status("cancelled")
                emit_threadsafe("download.cancelled", {"task": task.to_dict()})
                remove_active_download(task.id)
            except Exception:
                with self.lock:
                    if task.status != "cancelled":
                        task.update_status("failed")
                emit_threadsafe("download.failed", {"task": task.to_dict()})

        future.add_done_callback(_done)
        return task_id

    def preload_chapters(self, urls: List[str], callback: Optional[Callable] = None, max_retries: int = 2) -> List[str]:
        """并发预加载多个章节，返回 task_id 列表。callback 在单个任务完成时被调用，接收 task meta。"""
        ids = []
        for url in urls:
            tid = self._submit(url, callback=callback, max_retries=max_retries)
            ids.append(tid)
        return ids

    def batch_download(self, urls: List[str], callback: Optional[Callable] = None, max_retries: int = 2) -> str:
        """提交一批下载任务，返回一个 batch id（当前为 uuid），并在内部追踪每个任务。

        简化实现：返回一个 batch id，任务 id 可通过 inspect_tasks 查询。
        """
        batch_id = uuid.uuid4().hex
        for url in urls:
            self._submit(url, callback=callback, max_retries=max_retries)
        return batch_id

    def queue_download(self, url: str, callback: Optional[Callable] = None, max_retries: int = 2) -> str:
        """把单个下载任务加入队列并返回 task_id。"""
        return self._submit(url, callback=callback, max_retries=max_retries)

    def cancel_download(self, task_id: str) -> bool:
        """尝试取消任务；若任务已运行或完成可能取消失败。"""
        with self.lock:
            meta = self.tasks.get(task_id)
            if not meta:
                return False
            fut = meta.get("future")
            task: TaskInfo = meta.get("task")
            if fut and not fut.done():
                cancelled = fut.cancel()
                if cancelled:
                    task.update_status("cancelled")
                    emit_threadsafe("download.cancelled", {"task": task.to_dict()})
                    remove_active_download(task.id)
                return cancelled
            return False

    def retry_failed(self, task_id: str, callback: Optional[Callable] = None, max_retries: int = 2) -> Optional[str]:
        """重试单个失败任务，返回新的 task_id 或 None。"""
        with self.lock:
            meta = self.tasks.get(task_id)
            if not meta:
                return None
            task: TaskInfo = meta.get("task")
            if task.status != "failed":
                return None
            url = task.url
        return self._submit(url, callback=callback, max_retries=max_retries)

    def get_task(self, task_id: str) -> Optional[Dict]:
        with self.lock:
            meta = self.tasks.get(task_id)
            if not meta:
                return None
            # shallow copy
            return {k: (v.to_dict() if k == "task" else v) for k, v in meta.items() if k != "future"}

    def list_tasks(self) -> List[Dict]:
        with self.lock:
            return [{k: (v.to_dict() if k == "task" else v) for k, v in m.items() if k != "future"} for m in self.tasks.values()]

    def get_active_urls(self) -> List[str]:
        with self.lock:
            urls = []
            for meta in self.tasks.values():
                task: TaskInfo = meta.get("task")
                if task and task.status in ("pending", "running"):
                    urls.append(task.url)
            return urls
