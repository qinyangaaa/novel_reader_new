"""
Book DAO：仅负责 books 表的持久化操作
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, List

from ..db_manager import get_conn

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def add_book(book_info: Dict) -> Optional[int]:
    """插入或返回已存在的书籍 ID。"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO books (title, author, source_url, cover_url) VALUES (?, ?, ?, ?)",
            (book_info.get("title"), book_info.get("author", ""), book_info.get("source_url"), book_info.get("cover_url", "")),
        )
        conn.commit()
        cur.execute("SELECT id FROM books WHERE source_url = ?", (book_info.get("source_url"),))
        row = cur.fetchone()
        return int(row[0]) if row else None
    except Exception as e:
        logger.exception("book_dao.add_book 失败: %s", e)
        return None
    finally:
        conn.close()


def get_all_books() -> List[Dict]:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT id, title, author, source_url, cover_url, latest_chapter, last_read_chapter, last_read_index, created_at FROM books ORDER BY created_at DESC")
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.exception("book_dao.get_all_books 失败: %s", e)
        return []
    finally:
        conn.close()


def get_book_by_source(source_url: str) -> Optional[Dict]:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM books WHERE source_url = ?", (source_url,))
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.exception("book_dao.get_book_by_source 失败: %s", e)
        return None
    finally:
        conn.close()


def get_book_by_id(book_id: int) -> Optional[Dict]:
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT id, title, author, source_url, cover_url, latest_chapter, last_read_chapter, last_read_index, created_at FROM books WHERE id = ?",
            (book_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.exception("book_dao.get_book_by_id 失败: %s", e)
        return None
    finally:
        conn.close()


def update_last_read(book_id: int, chapter_index: int, chapter_title: str) -> bool:
    conn = get_conn()
    try:
        conn.execute("UPDATE books SET last_read_index = ?, last_read_chapter = ? WHERE id = ?", (chapter_index, chapter_title, book_id))
        conn.commit()
        return True
    except Exception as e:
        logger.exception("book_dao.update_last_read 失败: %s", e)
        return False
    finally:
        conn.close()


def delete_book(book_id: int) -> bool:
    conn = get_conn()
    try:
        # chapters 使用 ON DELETE CASCADE，删除 books 即可
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.exception("book_dao.delete_book 失败: %s", e)
        return False
    finally:
        conn.close()


def update_latest_chapter(book_id: int, latest_title: str) -> bool:
    """更新书籍的 latest_chapter 字段（DAO 层 CRUD 操作）。"""
    conn = get_conn()
    try:
        conn.execute("UPDATE books SET latest_chapter = ? WHERE id = ?", (latest_title, book_id))
        conn.commit()
        return True
    except Exception as e:
        logger.exception("book_dao.update_latest_chapter 失败: %s", e)
        return False
    finally:
        conn.close()
