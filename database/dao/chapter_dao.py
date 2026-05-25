"""
Chapter DAO：负责 chapters 表的持久化操作与分页支持
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, List

from ..db_manager import get_conn

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def save_chapter(chapter_info: Dict) -> Optional[int]:
    """保存章节（插入或更新），并标记为已下载。返回章节 id。"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO chapters (book_id, title, url, content, chapter_index, is_downloaded) VALUES (?, ?, ?, ?, ?, 1)",
            (chapter_info.get("book_id"), chapter_info.get("title"), chapter_info.get("url"), chapter_info.get("content", ""), chapter_info.get("chapter_index", 0)),
        )
        cur.execute("SELECT id FROM chapters WHERE book_id = ? AND chapter_index = ?", (chapter_info.get("book_id"), chapter_info.get("chapter_index")))
        row = cur.fetchone()
        if row:
            chap_id = int(row[0])
            cur.execute("UPDATE chapters SET content = ?, is_downloaded = 1 WHERE id = ?", (chapter_info.get("content", ""), chap_id))
        else:
            chap_id = cur.lastrowid
        conn.commit()
        return chap_id
    except Exception as e:
        logger.exception("chapter_dao.save_chapter 失败: %s", e)
        return None
    finally:
        conn.close()


def get_chapter_by_book_index(book_id: int, index: int) -> Optional[Dict]:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT id, book_id, title, url, content, chapter_index, is_downloaded FROM chapters WHERE book_id = ? AND chapter_index = ?", (book_id, index))
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.exception("chapter_dao.get_chapter_by_book_index 失败: %s", e)
        return None
    finally:
        conn.close()


def get_downloaded_chapters(book_id: int) -> List[Dict]:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT id, title, url, chapter_index FROM chapters WHERE book_id = ? AND is_downloaded = 1 ORDER BY chapter_index ASC", (book_id,))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.exception("chapter_dao.get_downloaded_chapters 失败: %s", e)
        return []
    finally:
        conn.close()


def delete_chapters_by_book(book_id: int) -> bool:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM chapters WHERE book_id = ?", (book_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.exception("chapter_dao.delete_chapters_by_book 失败: %s", e)
        return False
    finally:
        conn.close()


def get_chapters_page(book_id: int, offset: int = 0, limit: int = 100) -> List[Dict]:
    """分页获取章节（按 chapter_index 排序）。用于未来分页加载。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT id, title, url, chapter_index, is_downloaded FROM chapters WHERE book_id = ? ORDER BY chapter_index ASC LIMIT ? OFFSET ?",
            (book_id, limit, offset),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.exception("chapter_dao.get_chapters_page 失败: %s", e)
        return []
    finally:
        conn.close()
