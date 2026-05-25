"""
示例站点爬虫，演示如何继承 BaseCrawler 并注册到 registry。

注意：实际站点请把域名加入 supported_domains，并实现更稳健的解析。
"""
from __future__ import annotations

import time
from typing import Dict, Any

from ..base_crawler import BaseCrawler
from ..registry import get_session, register
from bs4 import BeautifulSoup


class ExampleSiteCrawler(BaseCrawler):
    name = "example_site"
    priority = 200
    supported_domains = ["example.com"]

    def __init__(self):
        super().__init__()
        self.session = get_session()

    def _wrap(self, ok: bool, data: Any = None, error: str | None = None) -> Dict:
        return {"ok": ok, "data": data, "error": error, "source": self.name}

    def search(self, keyword: str) -> Dict:
        # 示例实现：站点可能没有搜索 API，此处返回空
        return self._wrap(True, [], None)

    def get_book_info(self, book_url: str) -> Dict:
        try:
            r = self.session.get(book_url, timeout=8)
            soup = BeautifulSoup(r.text, "html.parser")
            title = (soup.title.string or "").strip() if soup.title else ""
            return self._wrap(True, {"title": title}, None)
        except Exception as e:
            return self._wrap(False, None, str(e))

    def get_chapter_list(self, book_url: str) -> Dict:
        try:
            r = self.session.get(book_url, timeout=8)
            soup = BeautifulSoup(r.text, "html.parser")
            links = []
            for i, a in enumerate(soup.select("a"), start=1):
                href = a.get("href")
                text = (a.get_text() or "").strip()
                if href and text:
                    links.append({"title": text, "url": href, "index": i})
            return self._wrap(True, links, None)
        except Exception as e:
            return self._wrap(False, None, str(e))

    def fetch_chapter(self, chapter_url: str) -> Dict:
        try:
            r = self.session.get(chapter_url, timeout=8)
            soup = BeautifulSoup(r.text, "html.parser")
            title = (soup.title.string or "").strip() if soup.title else ""
            content = soup.get_text("\n", strip=True)
            return self._wrap(True, {"title": title, "content": content}, None)
        except Exception as e:
            return self._wrap(False, None, str(e))

    def health_check(self) -> Dict:
        try:
            t0 = time.time()
            r = self.session.get("https://example.com", timeout=5)
            lat = time.time() - t0
            return {"ok": r.status_code == 200, "latency": lat, "error": None if r.status_code == 200 else f"status {r.status_code}"}
        except Exception as e:
            return {"ok": False, "latency": 0.0, "error": str(e)}


# 实例化并注册到 registry
_inst = ExampleSiteCrawler()
register(_inst, priority=_inst.priority)

__all__ = ["_inst", "ExampleSiteCrawler"]
