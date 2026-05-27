"""
Crawler 调度服务：负责选择 crawler、fallback、重试与自动失效切换。

注意：此模块不进行解析、数据库或 UI 操作，仅协调 crawler 并返回统一数据结构。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from . import BookService
from ..crawlers import get_crawler_by_url, get_available_crawlers
from ..crawlers.registry import mark_failure, mark_success
from ..plugins import source_manager

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class CrawlerService:
    """封装 crawler 的选择与失败处理逻辑。

    所有方法返回统一 dict：{"ok": bool, "data": Any, "error": Optional[str], "crawler": Optional[str]}
    """

    @staticmethod
    def get_best_crawler(url: str) -> List:
        """根据 URL 返回候选 crawler 列表，按优先级排序。"""
        try:
            candidates = get_crawler_by_url(url)
            return candidates
        except Exception as e:
            logger.exception("get_best_crawler 异常: %s", e)
            return []

    @staticmethod
    def _unify(ok: bool, data: Any = None, error: Optional[str] = None, crawler: Optional[str] = None) -> Dict:
        return {"ok": ok, "data": data, "error": error, "crawler": crawler}

    @staticmethod
    def fetch_chapter(url: str, timeout: Optional[int] = None, per_crawler_retries: int = 1) -> Dict:
        """抓取章节：按候选 crawler 顺序尝试，失败时自动 fallback 下一个。

        调用方应在后台线程/Executor 中执行此方法以避免阻塞 UI。
        """
        candidates = CrawlerService.get_best_crawler(url)
        if not candidates:
            return CrawlerService._unify(False, None, "no_crawlers", None)
        last_error = None
        for crawler in candidates:
            name = getattr(crawler, "name", str(crawler))
            for attempt in range(per_crawler_retries):
                try:
                    resp = crawler.fetch_chapter(url)
                    if resp.get("ok"):
                        mark_success(name)
                        return CrawlerService._unify(True, resp.get("data"), None, name)
                    else:
                        last_error = resp.get("error")
                        # 标记失败并尝试下一个 crawler
                        mark_failure(name)
                except Exception as e:
                    last_error = str(e)
                    logger.exception("fetch_chapter 调用 crawler 异常: %s", e)
                    mark_failure(name)
            # 该 crawler all retries failed -> try next
        return CrawlerService._unify(False, None, last_error or "all_failed", None)

    @staticmethod
    def fetch_chapter_list(url: str, per_crawler_retries: int = 1) -> Dict:
        """获取章节列表，支持 fallback 与重试。"""
        candidates = CrawlerService.get_best_crawler(url)
        if not candidates:
            return CrawlerService._unify(False, None, "no_crawlers", None)
        last_error = None
        for crawler in candidates:
            name = getattr(crawler, "name", str(crawler))
            for attempt in range(per_crawler_retries):
                try:
                    resp = crawler.get_chapter_list(url)
                    if resp.get("ok"):
                        mark_success(name)
                        return CrawlerService._unify(True, resp.get("data"), None, name)
                    else:
                        last_error = resp.get("error")
                        mark_failure(name)
                except Exception as e:
                    last_error = str(e)
                    logger.exception("fetch_chapter_list 异常: %s", e)
                    mark_failure(name)
        return CrawlerService._unify(False, None, last_error or "all_failed", None)

    @staticmethod
    def search(keyword: str, max_try_crawlers: int = 3) -> Dict:
        """搜索：按优先级轮询可用 crawler，直到获得非空结果或耗尽候选。

        注意：搜索通常比抓取更依赖站点能力，建议由上层决定并发与节流策略。
        """
        try:
            source_results = source_manager.search_books(keyword, max_sources=8, max_results=30)
            if source_results:
                return CrawlerService._unify(True, source_results, None, "source_manager")

            candidates = get_available_crawlers()
            tries = 0
            for crawler in candidates:
                if tries >= max_try_crawlers:
                    break
                tries += 1
                try:
                    resp = crawler.search(keyword)
                    name = getattr(crawler, "name", None)
                    if resp.get("ok") and resp.get("data"):
                        mark_success(name)
                        return CrawlerService._unify(True, resp.get("data"), None, name)
                    else:
                        mark_failure(name)
                except Exception as e:
                    logger.exception("search 调用异常: %s", e)
            return CrawlerService._unify(True, [], None, None)
        except Exception as e:
            logger.exception("CrawlerService.search 异常: %s", e)
            return CrawlerService._unify(False, None, str(e), None)

    @staticmethod
    def auto_fallback_check(timeout: int = 5) -> Dict:
        """对已注册的 crawler 执行简单健康检查，并根据结果触发自动失效/恢复。

        返回检查摘要。
        """
        try:
            candidates = get_available_crawlers()
            summary = []
            for c in candidates:
                name = getattr(c, "name", None)
                try:
                    h = c.health_check()
                    summary.append({"name": name, "ok": h.get("ok"), "latency": h.get("latency"), "error": h.get("error")})
                    if not h.get("ok"):
                        mark_failure(name)
                    else:
                        mark_success(name)
                except Exception as e:
                    logger.exception("auto_fallback_check 异常: %s", e)
                    mark_failure(name)
                    summary.append({"name": name, "ok": False, "latency": 0, "error": str(e)})
            return CrawlerService._unify(True, summary, None, None)
        except Exception as e:
            logger.exception("auto_fallback_check 总体异常: %s", e)
            return CrawlerService._unify(False, None, str(e), None)
