"""
BaseCrawler 抽象基类，定义爬虫必须实现的接口。

约定：所有网络请求使用 registry.get_session() 提供的共享 session，所有返回统一 dict。
"""
from __future__ import annotations

import abc
from typing import Any, Dict, Optional


class BaseCrawler(abc.ABC):
    """所有网站爬虫应继承此类并实现抽象方法。

    统一返回格式：{"ok": bool, "data": Any, "error": Optional[str], "source": str}
    health_check 返回：{"ok": bool, "latency": float, "error": Optional[str]}
    """

    name: str = "base"
    priority: int = 100
    supported_domains: Optional[list] = None  # 子类可声明支持的域名列表

    def __init__(self) -> None:
        super().__init__()

    @abc.abstractmethod
    def search(self, keyword: str) -> Dict:
        """站内搜索，返回统一结构。"""

    @abc.abstractmethod
    def get_book_info(self, book_url: str) -> Dict:
        """获取书籍元信息（title, author, cover, description 等）。"""

    @abc.abstractmethod
    def get_chapter_list(self, book_url: str) -> Dict:
        """获取章节列表，返回 {'ok': True, 'data': [{'title','url','index'},...], 'error':None}。"""

    @abc.abstractmethod
    def fetch_chapter(self, chapter_url: str) -> Dict:
        """抓取单个章节正文，返回 {'ok', 'data': {'title','content'}, 'error'}。"""

    @abc.abstractmethod
    def health_check(self) -> Dict:
        """针对站点的健康检查，返回 {'ok', 'latency', 'error'}。"""
