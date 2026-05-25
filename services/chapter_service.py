"""
章节服务：负责章节获取、下载与缓存钩子。

设计原则：
- 不直接依赖爬虫，接受外部 fetcher（可注入爬虫函数或对象）
- 所有耗时操作应在 UI 线程外执行（这里留接口，可用线程池/Executor 调用）
- 只调用 DAO，不直接操作 UI
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional, Callable

from ..database.dao import chapter_dao

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# 简单的内存缓存占位，后续可替换为 Redis / disk cache / blob store
_in_memory_cache: Dict[int, Dict] = {}
_chapter_key_cache: Dict[tuple[int, int], Dict] = {}
_chapter_url_cache: Dict[str, Dict] = {}


class ChapterService:
    """章节业务服务，统一返回结构：{"ok": bool, "data": Any, "error": Optional[str]}"""

    @staticmethod
    def get_chapter(book_id: int, index: int) -> Dict:
        """获取本地已保存的章节内容。

        如果章节不存在，返回 ok=False 且 data=None。
        """
        try:
            cached = _chapter_key_cache.get((book_id, index))
            if cached and cached.get("content"):
                return {"ok": True, "data": dict(cached), "error": None}
            row = chapter_dao.get_chapter_by_book_index(book_id, index)
            if not row:
                return {"ok": False, "data": None, "error": "not_found"}
            ChapterService._cache_chapter_record(row)
            return {"ok": True, "data": row, "error": None}
        except Exception as e:
            logger.exception("ChapterService.get_chapter 异常: %s", e)
            return {"ok": False, "data": None, "error": str(e)}

    @staticmethod
    def download_chapter(book_id: int, chapter_index: int, chapter_url: str, fetcher: Optional[Callable[[str], Dict]] = None) -> Dict:
        """下载单个章节：

        - `fetcher` 是一个可调用对象，接受 `chapter_url`，返回 {'title':..., 'content':...}
        - service 不直接实现抓取逻辑，需由爬虫层传入 fetcher
        """
        if fetcher is None:
            return {"ok": False, "data": None, "error": "no_fetcher_provided"}
        try:
            result = fetcher(chapter_url)
            if not result or 'content' not in result:
                return {"ok": False, "data": None, "error": "fetch_failed"}
            chap = {
                "book_id": book_id,
                "title": result.get('title') or f"第{chapter_index}章",
                "url": chapter_url,
                "content": result.get('content'),
                "chapter_index": chapter_index,
            }
            cid = chapter_dao.save_chapter(chap)
            # 同步缓存钩子
            if cid:
                ChapterService.cache_chapter(cid, chap)
            return {"ok": True, "data": {"chapter_id": cid}, "error": None}
        except Exception as e:
            logger.exception("ChapterService.download_chapter 异常: %s", e)
            return {"ok": False, "data": None, "error": str(e)}

    @staticmethod
    def preload_chapters(book_id: int, start_index: int, count: int, fetcher: Optional[Callable[[str], Dict]] = None, url_resolver: Optional[Callable[[int], str]] = None, executor: Optional[Any] = None) -> Dict:
        """预加载一段连续章节：

        参数：
        - `fetcher(chapter_url)`：必须提供，用于抓取章节内容
        - `url_resolver(index) -> url`：将章节序号映射为章节 URL 的可选回调
        - `executor`：可选的并发执行器（ThreadPoolExecutor）以并行下载

        返回：下载结果摘要
        """
        if fetcher is None:
            return {"ok": False, "data": None, "error": "no_fetcher_provided"}
        results = []
        try:
            indices = range(start_index, start_index + count)
            if executor:
                # 并发执行
                futures = {}
                for idx in indices:
                    if url_resolver:
                        url = url_resolver(idx)
                    else:
                        return {"ok": False, "data": None, "error": "no_url_resolver"}
                    futures[executor.submit(fetcher, url)] = (idx, url)
                for fut in futures:
                    idx, url = futures[fut]
                    try:
                        res = fut.result()
                        if res and 'content' in res:
                            chap = {"book_id": book_id, "title": res.get('title'), "url": url, "content": res.get('content'), "chapter_index": idx}
                            cid = chapter_dao.save_chapter(chap)
                            ChapterService.cache_chapter(cid, chap)
                            results.append({"index": idx, "ok": True, "chapter_id": cid})
                        else:
                            results.append({"index": idx, "ok": False, "error": "fetch_failed"})
                    except Exception as e:
                        logger.exception("preload future 异常: %s", e)
                        results.append({"index": idx, "ok": False, "error": str(e)})
            else:
                # 顺序执行
                for idx in indices:
                    if url_resolver is None:
                        return {"ok": False, "data": None, "error": "no_url_resolver"}
                    url = url_resolver(idx)
                    res = fetcher(url)
                    if res and 'content' in res:
                        chap = {"book_id": book_id, "title": res.get('title'), "url": url, "content": res.get('content'), "chapter_index": idx}
                        cid = chapter_dao.save_chapter(chap)
                        ChapterService.cache_chapter(cid, chap)
                        results.append({"index": idx, "ok": True, "chapter_id": cid})
                    else:
                        results.append({"index": idx, "ok": False, "error": "fetch_failed"})
            return {"ok": True, "data": results, "error": None}
        except Exception as e:
            logger.exception("ChapterService.preload_chapters 异常: %s", e)
            return {"ok": False, "data": None, "error": str(e)}

    @staticmethod
    def get_downloaded_chapters(book_id: int) -> Dict:
        """返回已下载章节列表（供 UI 或后台展示）。"""
        try:
            rows = chapter_dao.get_downloaded_chapters(book_id)
            for row in rows:
                ChapterService._cache_chapter_record(row)
            return {"ok": True, "data": rows, "error": None}
        except Exception as e:
            logger.exception("ChapterService.get_downloaded_chapters 异常: %s", e)
            return {"ok": False, "data": [], "error": str(e)}

    @staticmethod
    def list_chapters(book_id: int, offset: int = 0, limit: int = 500) -> Dict:
        """分页列出本地章节元数据。"""
        try:
            rows = chapter_dao.get_chapters_page(book_id, offset=offset, limit=limit)
            for row in rows:
                ChapterService._cache_chapter_record(row)
            return {"ok": True, "data": rows, "error": None}
        except Exception as e:
            logger.exception("ChapterService.list_chapters 异常: %s", e)
            return {"ok": False, "data": [], "error": str(e)}

    @staticmethod
    def store_fetched_chapter(book_id: int, chapter_index: int, chapter_url: str, fetched: Dict) -> Dict:
        """把已抓取的章节内容落到本地数据库。"""
        try:
            content = fetched.get("data") if fetched.get("ok") else None
            if not content:
                return {"ok": False, "data": None, "error": fetched.get("error") or "no_content"}
            chapter_info = {
                "book_id": book_id,
                "title": content.get("title") or f"第{chapter_index + 1}章",
                "url": chapter_url,
                "content": content.get("content", ""),
                "chapter_index": chapter_index,
            }
            chapter_id = chapter_dao.save_chapter(chapter_info)
            if chapter_id is None:
                return {"ok": False, "data": None, "error": "save_failed"}
            ChapterService.cache_chapter(chapter_id, chapter_info)
            return {"ok": True, "data": {"chapter_id": chapter_id}, "error": None}
        except Exception as e:
            logger.exception("ChapterService.store_fetched_chapter 异常: %s", e)
            return {"ok": False, "data": None, "error": str(e)}

    @staticmethod
    def has_local_chapter(book_id: int, chapter_index: int) -> bool:
        cached = _chapter_key_cache.get((book_id, chapter_index))
        if cached and cached.get("content"):
            return True
        row = chapter_dao.get_chapter_by_book_index(book_id, chapter_index)
        if not row:
            return False
        ChapterService._cache_chapter_record(row)
        return bool(row.get("content"))

    @staticmethod
    def get_cached_by_url(chapter_url: str) -> Optional[Dict]:
        cached = _chapter_url_cache.get(chapter_url)
        return dict(cached) if cached else None

    @staticmethod
    def cache_chapter(chapter_id: Optional[int], chapter_info: Dict) -> Dict:
        """缓存章节的占位方法：未来可接入磁盘或分布式缓存。

        当前实现为简单内存缓存，非持久化。
        """
        try:
            if chapter_id is None:
                return {"ok": False, "data": None, "error": "no_chapter_id"}
            normalized = dict(chapter_info)
            normalized["id"] = chapter_id
            _in_memory_cache[chapter_id] = normalized
            ChapterService._cache_chapter_record(normalized)
            return {"ok": True, "data": None, "error": None}
        except Exception as e:
            logger.exception("ChapterService.cache_chapter 异常: %s", e)
            return {"ok": False, "data": None, "error": str(e)}

    @staticmethod
    def _cache_chapter_record(chapter_info: Dict) -> None:
        book_id = chapter_info.get("book_id")
        chapter_index = chapter_info.get("chapter_index")
        chapter_url = chapter_info.get("url")
        if book_id is not None and chapter_index is not None:
            _chapter_key_cache[(int(book_id), int(chapter_index))] = dict(chapter_info)
        if chapter_url:
            _chapter_url_cache[str(chapter_url)] = dict(chapter_info)
