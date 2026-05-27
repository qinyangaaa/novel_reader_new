from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import trafilatura

from ..plugins import source_manager
from .base_crawler import BaseCrawler
from .registry import get_session, mark_failure, mark_success


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class UniversalCrawler(BaseCrawler):
    name = "universal"
    priority = 1000

    def __init__(self, timeout: int = 10):
        super().__init__()
        self.session = get_session()
        self.timeout = timeout

    def _unify(self, ok: bool, data: Any = None, error: str | None = None) -> Dict:
        return {"ok": ok, "data": data, "error": error, "source": self.name}

    def _get_response(self, url: str):
        candidates = [url]
        parsed = urlparse(url)
        if parsed.scheme == "https":
            candidates.append("http://" + parsed.netloc + parsed.path + (f"?{parsed.query}" if parsed.query else ""))
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                resp = self.session.get(candidate, timeout=self.timeout)
                resp.raise_for_status()
                try:
                    resp.encoding = resp.apparent_encoding
                except Exception:
                    pass
                return resp
            except Exception as e:
                last_error = e
                continue
        if last_error:
            raise last_error
        raise RuntimeError("request failed")

    def search(self, keyword: str) -> Dict:
        """先发现小说站，再在这些站点中搜索小说。"""
        if not keyword.strip():
            return self._unify(True, [], None)
        try:
            results = source_manager.search_books(keyword, max_sources=8, max_results=30)
            mark_success(self.name)
            return self._unify(True, results, None)
        except Exception as e:
            logger.debug("UniversalCrawler.search failed: %s", e)
            mark_failure(self.name)
            return self._unify(False, None, str(e))

    def get_book_info(self, book_url: str) -> Dict:
        try:
            resp = self._get_response(book_url)
            soup = BeautifulSoup(resp.text, "html.parser")
            title = (soup.title.string or "").strip() if soup.title else ""
            author = ""
            cover = ""
            desc = ""
            author_node = soup.select_one("meta[name=author]") or soup.select_one(".author")
            if author_node:
                author = author_node.get("content") or author_node.get_text(" ", strip=True)
            image_node = soup.select_one("meta[property='og:image']") or soup.select_one("img")
            if image_node:
                cover = image_node.get("content") or image_node.get("src") or ""
            desc_node = soup.select_one("meta[name=description]")
            if desc_node:
                desc = desc_node.get("content") or ""
            mark_success(self.name)
            return self._unify(True, {"title": title, "author": author, "cover": cover, "description": desc}, None)
        except Exception as e:
            logger.debug("UniversalCrawler.get_book_info failed: %s", e)
            mark_failure(self.name)
            return self._unify(False, None, str(e))

    def get_chapter_list(self, book_url: str) -> Dict:
        try:
            resp = self._get_response(book_url)
            base_url = resp.url or book_url
            soup = BeautifulSoup(resp.text, "html.parser")
            candidates = []
            for selector in ("#list", "#chapterlist", ".chapterlist", ".booklist", ".mulu", ".catalog"):
                candidates.extend(soup.select(selector))
            for name in ("list", "chapterlist", "chapter", "booklist", "mulu", "catalog"):
                candidates.extend(soup.find_all(id=re.compile(name, re.I)))
                candidates.extend(soup.find_all(class_=re.compile(name, re.I)))
            if not candidates:
                candidates = [soup]
            links = []
            seen = set()
            for container in candidates:
                for item in container.find_all("a", href=True):
                    title = item.get_text(" ", strip=True)
                    href = item.get("href")
                    if not href or not title:
                        continue
                    if not self._looks_like_chapter_title(title):
                        continue
                    if not urlparse(href).netloc:
                        href = urljoin(base_url, href)
                    if href in seen:
                        continue
                    seen.add(href)
                    links.append({"title": title, "url": href, "index": len(links) + 1})
            if links and any(word in links[0]["title"] for word in ("大结局", "完结", "最后")):
                links.reverse()
                for index, chapter in enumerate(links, start=1):
                    chapter["index"] = index
            mark_success(self.name)
            return self._unify(True, links, None)
        except Exception as e:
            logger.debug("UniversalCrawler.get_chapter_list failed: %s", e)
            mark_failure(self.name)
            return self._unify(False, None, str(e))

    def _looks_like_chapter_title(self, title: str) -> bool:
        title = title.strip()
        if not title:
            return False
        if re.search(r"第.{1,12}[章节回卷集]", title):
            return True
        if any(word in title for word in ("序章", "楔子", "正文", "番外", "大结局")):
            return True
        return bool(re.match(r"^\d+[\.\s、_-]", title))

    def fetch_chapter(self, chapter_url: str) -> Dict:
        try:
            resp = self._get_response(chapter_url)
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")
            title = (soup.title.string or "").strip() if soup.title else ""
            try:
                text = trafilatura.extract(html)
                if text and text.strip():
                    mark_success(self.name)
                    return self._unify(True, {"title": title, "content": text.strip()}, None)
            except Exception:
                pass
            content = ""
            for selector in ("#content", ".content", ".read-content", ".chapter-content", "article"):
                node = soup.select_one(selector)
                if node:
                    content = node.get_text("\n", strip=True)
                    break
            if not content:
                for node in soup(["script", "style"]):
                    node.extract()
                content = soup.get_text("\n", strip=True)
            mark_success(self.name)
            return self._unify(True, {"title": title, "content": content}, None)
        except Exception as e:
            logger.debug("UniversalCrawler.fetch_chapter failed: %s", e)
            mark_failure(self.name)
            return self._unify(False, None, str(e))

    def health_check(self) -> Dict:
        try:
            started = time.time()
            resp = self.session.get("https://yandex.com", timeout=self.timeout)
            latency = time.time() - started
            ok = resp.status_code < 500
            if ok:
                mark_success(self.name)
                return {"ok": True, "latency": latency, "error": None}
            mark_failure(self.name)
            return {"ok": False, "latency": latency, "error": f"status {resp.status_code}"}
        except Exception as e:
            mark_failure(self.name)
            return {"ok": False, "latency": 0.0, "error": str(e)}


universal = UniversalCrawler()

__all__ = ["universal", "UniversalCrawler"]
