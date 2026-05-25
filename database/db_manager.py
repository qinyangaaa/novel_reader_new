"""
数据库连接工厂（线程安全、为 Android 配置）

提供：`get_conn()` 用于获取新的 sqlite3.Connection，所有 DAO/Service 应通过该工厂获取连接，
避免在模块级持有全局连接。
"""
from __future__ import annotations

import sqlite3
from typing import Optional
from .models import get_db_path, init_db

# 初始化数据库结构（确保表和索引存在）
init_db()


def get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    """返回一个新的 sqlite3.Connection。配置适合 Android 的参数：
    - check_same_thread=False 允许多个线程使用不同的连接
    - row_factory=sqlite3.Row 以便返回字典样式结果
    - 启用 PRAGMA 以确保 WAL 与外键
    注意：不要在模块级保存此连接，调用方需负责关闭连接。
    """
    if db_path is None:
        db_path = get_db_path()
    # 确保 DB 已初始化
    init_db(db_path)
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # 运行必要的 PRAGMA
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn
