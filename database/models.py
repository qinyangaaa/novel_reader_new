"""
数据库模型与初始化

负责创建 novels.db 数据库及所需表结构。
数据库路径：项目根的 data/novels.db
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def get_db_path() -> str:
    """返回默认数据库文件路径：novel_reader/data/novels.db，必要时创建目录。"""
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "novels.db")


def init_db(db_path: str | None = None) -> None:
    """初始化数据库并创建表与索引。启用 WAL 与外键约束。

    设计要点：
    - 使用 WAL 模式提高并发写入性能
    - 外键使用 ON DELETE CASCADE，以便删除书籍时自动删除章节
    - chapters 使用 UNIQUE(book_id, chapter_index) 确保同一本书的章节序号唯一
    - 添加必要的索引以支持分页与快速查询
    """
    if db_path is None:
        db_path = get_db_path()

    # 为 Android/多线程场景建议使用 check_same_thread=False 在连接时（在 DAO 层统一设置）
    conn = sqlite3.connect(db_path)
    try:
        # 启用 WAL 模式和外键
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA synchronous = NORMAL;")

        # 创建 books 表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT DEFAULT '',
                source_url TEXT UNIQUE,
                cover_url TEXT DEFAULT '',
                latest_chapter TEXT DEFAULT '',
                last_read_chapter TEXT DEFAULT '',
                last_read_index INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        # 创建 chapters 表，使用 ON DELETE CASCADE
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                url TEXT UNIQUE,
                content TEXT DEFAULT '',
                chapter_index INTEGER DEFAULT 0,
                is_downloaded INTEGER DEFAULT 0,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                UNIQUE(book_id, chapter_index)
            )
            """
        )

        # 索引：根据 book_id 和 chapter_index 快速定位与分页
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chapters_book_index ON chapters(book_id, chapter_index);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_books_source_url ON books(source_url);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chapters_url ON chapters(url);")

        conn.commit()
    except Exception as e:
        logger.exception("初始化数据库失败：%s", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    init_db()
