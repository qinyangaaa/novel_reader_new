"""crawlers 包入口：导出 registry 与 base_crawler 等公共 API。"""
from .registry import register, unregister, get_available_crawlers, get_crawler_by_url, get_session
from .base_crawler import BaseCrawler
from .universal_crawler import universal as universal_crawler

__all__ = ["register", "unregister", "get_available_crawlers", "get_crawler_by_url", "get_session", "BaseCrawler", "universal_crawler"]
