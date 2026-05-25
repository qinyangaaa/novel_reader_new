"""兜底通用爬虫实现，作为最后的 fallback（优先级最低）。

设计：继承 BaseCrawler，使用 registry 提供的共享 session，尽量用 trafilatura + BeautifulSoup 提炼信息。
不要在此处写针对站点的大量 if/else，具体站点解析应由 sites 中的爬虫实现。
"""
from __future__ import annotations

import logging
import re
import time
from typing import Dict, Any, List
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import trafilatura

from .base_crawler import BaseCrawler
from .registry import get_session, mark_failure, mark_success

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class UniversalCrawler(BaseCrawler):
    name = "universal"
    priority = 1000  # 兜底优先级最低

    def __init__(self, timeout: int = 10):
        super().__init__()
        self.session = get_session()
        self.timeout = timeout

    def _unify(self, ok: bool, data: Any = None, error: str | None = None) -> Dict:
        return {"ok": ok, "data": data, "error": error, "source": self.name}

    def search(self, keyword: str) -> Dict:
        # 兜底：使用通用搜索（如 Google/Bing）未实现，返回空
        return self._unify(True, [], None)

    def get_book_info(self, book_url: str) -> Dict:
        try:
            t0 = time.time()
            resp = self.session.get(book_url, timeout=self.timeout)
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")
            title = (soup.title.string or "").strip() if soup.title else ""
            # 尝试提取作者/封面/简介的常见选择器
            author = ""
            cover = ""
            desc = ""
            # 简单启发式查找
            auth_node = soup.select_one("meta[name=author]") or soup.select_one(".author")
            if auth_node and auth_node.get("content"):
                author = auth_node.get("content")
            img = soup.select_one("meta[property='og:image']") or soup.select_one("img")
            if img and img.get("content"):
                cover = img.get("content")
            # 简要描述
            dnode = soup.select_one("meta[name=description]")
            if dnode and dnode.get("content"):
                desc = dnode.get("content")
            mark_success(self.name)
            return self._unify(True, {"title": title, "author": author, "cover": cover, "description": desc}, None)
        except Exception as e:
            logger.debug("UniversalCrawler.get_book_info 失败: %s", e)
            mark_failure(self.name)
            return self._unify(False, None, str(e))

    def get_chapter_list(self, book_url: str) -> Dict:
        try:
            resp = self.session.get(book_url, timeout=self.timeout)
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")
            candidates = []
            for id_name in ("list", "chapterlist", "chapter", "booklist", "mulu"):
                candidates.extend(soup.find_all(id=re.compile(id_name, re.I)))
                candidates.extend(soup.find_all(class_=re.compile(id_name, re.I)))
            if not candidates:
                candidates = [soup]
            links = []
            seen = set()
            idx = 0
            for c in candidates:
                for a in c.find_all("a", href=True):
                    text = (a.get_text() or "").strip()
                    href = a.get("href")
                    if not href or not text:
                        continue
                    if not urlparse(href).netloc:
                        href = urljoin(book_url, href)
                    if href in seen:
                        continue
                    seen.add(href)
                    idx += 1
                    links.append({"title": text, "url": href, "index": idx})
            mark_success(self.name)
            return self._unify(True, links, None)
        except Exception as e:
            logger.debug("UniversalCrawler.get_chapter_list 失败: %s", e)
            mark_failure(self.name)
            return self._unify(False, None, str(e))

    def fetch_chapter(self, chapter_url: str) -> Dict:
        try:
            resp = self.session.get(chapter_url, timeout=self.timeout)
            html = resp.text
            # trafilatura 优先
            try:
                text = trafilatura.extract(html)
                if text and text.strip():
                    soup = BeautifulSoup(html, "html.parser")
                    title = (soup.title.string or "").strip() if soup.title else ""
                    mark_success(self.name)
                    return self._unify(True, {"title": title, "content": text.strip()}, None)
            except Exception:
                pass
            soup = BeautifulSoup(html, "html.parser")
            title = (soup.title.string or "").strip() if soup.title else ""
            content = ""
            for selector in ("#content", ".content", ".read-content", ".chapter-content", "article"):
                node = soup.select_one(selector)
                if node:
                    content = node.get_text("\n", strip=True)
                    break
            if not content:
                for s in soup(["script", "style"]):
                    s.extract()
                content = soup.get_text("\n", strip=True)
            mark_success(self.name)
            return self._unify(True, {"title": title, "content": content}, None)
        except Exception as e:
            logger.debug("UniversalCrawler.fetch_chapter 失败: %s", e)
            mark_failure(self.name)
            return self._unify(False, None, str(e))

    def health_check(self) -> Dict:
        try:
            t0 = time.time()
            r = self.session.get("https://www.baidu.com", timeout=self.timeout)
            latency = time.time() - t0
            ok = r.status_code == 200
            if ok:
                mark_success(self.name)
                return {"ok": True, "latency": latency, "error": None}
            else:
                mark_failure(self.name)
                return {"ok": False, "latency": latency, "error": f"status {r.status_code}"}
        except Exception as e:
            mark_failure(self.name)
            return {"ok": False, "latency": 0.0, "error": str(e)}


universal = UniversalCrawler()

__all__ = ["universal", "UniversalCrawler"]
