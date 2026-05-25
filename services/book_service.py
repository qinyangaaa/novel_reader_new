"""
书籍服务：负责书籍相关的业务逻辑、组合数据与异常处理。

注意：UI 不应直接调用 DAO，应通过此服务层。
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional

from ..database.dao import book_dao

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class BookService:
    """BookService 封装书籍相关业务逻辑。

    返回统一数据结构：{"ok": bool, "data": Any, "error": Optional[str]}
    """

    @staticmethod
    def add_book(book_info: Dict) -> Dict:
        """添加书籍：调用 DAO 插入或返回已存在的 book_id。

        参数：book_info 包含 title, author, source_url, cover_url
        返回：统一 dict
        """
        try:
            bid = book_dao.add_book(book_info)
            return {"ok": True, "data": {"book_id": bid}, "error": None}
        except Exception as e:
            logger.exception("BookService.add_book 异常: %s", e)
            return {"ok": False, "data": None, "error": str(e)}

    @staticmethod
    def remove_book(book_id: int) -> Dict:
        """删除书籍（以及其章节，依赖 ON DELETE CASCADE）。"""
        try:
            ok = book_dao.delete_book(book_id)
            return {"ok": ok, "data": None if ok else None, "error": None if ok else "delete failed"}
        except Exception as e:
            logger.exception("BookService.remove_book 异常: %s", e)
            return {"ok": False, "data": None, "error": str(e)}

    @staticmethod
    def list_books() -> Dict:
        """列出所有书籍，返回书籍字典列表。"""
        try:
            books = book_dao.get_all_books()
            return {"ok": True, "data": books, "error": None}
        except Exception as e:
            logger.exception("BookService.list_books 异常: %s", e)
            return {"ok": False, "data": [], "error": str(e)}

    @staticmethod
    def get_book(book_id: int) -> Dict:
        """按 ID 获取单本书信息。"""
        try:
            book = book_dao.get_book_by_id(book_id)
            if not book:
                return {"ok": False, "data": None, "error": "not_found"}
            return {"ok": True, "data": book, "error": None}
        except Exception as e:
            logger.exception("BookService.get_book 异常: %s", e)
            return {"ok": False, "data": None, "error": str(e)}

    @staticmethod
    def update_read_progress(book_id: int, chapter_index: int, chapter_title: str) -> Dict:
        """更新阅读进度（last_read_index, last_read_chapter）。"""
        try:
            ok = book_dao.update_last_read(book_id, chapter_index, chapter_title)
            return {"ok": ok, "data": None, "error": None if ok else "update failed"}
        except Exception as e:
            logger.exception("BookService.update_read_progress 异常: %s", e)
            return {"ok": False, "data": None, "error": str(e)}

    @staticmethod
    def update_latest_chapter(book_id: int, latest_title: str) -> Dict:
        """更新书籍的 latest_chapter 字段（供爬虫或下载器调用）。"""
        try:
            ok = book_dao.update_latest_chapter(book_id, latest_title)
            return {"ok": ok, "data": None, "error": None if ok else "update failed"}
        except Exception as e:
            logger.exception("BookService.update_latest_chapter 异常: %s", e)
            return {"ok": False, "data": None, "error": str(e)}
