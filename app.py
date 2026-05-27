from __future__ import annotations

import logging
import sys
import threading
import traceback
import types
from pathlib import Path
from typing import Any

import flet as ft


ROOT = Path(__file__).resolve().parent
ICONS = getattr(ft, "Icons", None) or getattr(ft, "icons")
COLORS = getattr(ft, "Colors", None) or getattr(ft, "colors")


def crash_handler(exc_type, exc_value, exc_tb) -> None:
    for path in (Path("/sdcard/novel_reader_error.txt"), Path("novel_reader_error.txt")):
        try:
            with path.open("w", encoding="utf-8") as f:
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
            return
        except Exception:
            pass


sys.excepthook = crash_handler

if "novel_reader" not in sys.modules:
    pkg = types.ModuleType("novel_reader")
    pkg.__path__ = [str(ROOT)]
    sys.modules["novel_reader"] = pkg

from novel_reader.services.book_service import BookService
from novel_reader.services.chapter_service import ChapterService
from novel_reader.services.crawler_service import CrawlerService


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _title(item: dict[str, Any]) -> str:
    return str(item.get("title") or item.get("name") or "未命名")


def _author(item: dict[str, Any]) -> str:
    return str(item.get("author") or item.get("source") or "未知来源")


def _url(item: dict[str, Any]) -> str:
    return str(item.get("source_url") or item.get("book_url") or item.get("url") or "")


class FletNovelReader:
    def __init__(self, page: ft.Page):
        self.page = page
        self.books: list[dict[str, Any]] = []
        self.search_results: list[dict[str, Any]] = []
        self.searching = False
        self.current_book: dict[str, Any] | None = None
        self.current_chapters: list[dict[str, Any]] = []
        self.current_chapter_index = 1

        self.status = ft.Text("", color=COLORS.RED_700)
        self.bookshelf_list = ft.ListView(expand=True, spacing=6)
        self.search_input = ft.TextField(label="搜索小说", expand=True, on_submit=lambda _: self.search())
        self.search_list = ft.ListView(expand=True, spacing=6)
        self.reader_title = ft.Text("请选择一本书", size=20, weight=ft.FontWeight.BOLD)
        self.reader_body = ft.Text("章节内容会显示在这里。", selectable=True)
        self.reader_scroll = ft.ListView(expand=True, controls=[self.reader_title, self.reader_body])

        self.bookshelf_view = ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("书架", size=22, weight=ft.FontWeight.BOLD, expand=True),
                        ft.IconButton(icon=ICONS.REFRESH, tooltip="刷新", on_click=lambda _: self.load_books()),
                    ]
                ),
                self.bookshelf_list,
            ],
        )
        self.search_view = ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    controls=[
                        self.search_input,
                        ft.IconButton(icon=ICONS.SEARCH, tooltip="搜索", on_click=lambda _: self.search()),
                    ]
                ),
                self.search_list,
            ],
        )
        self.reader_view = ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.IconButton(icon=ICONS.ARROW_BACK, tooltip="上一章", on_click=lambda _: self.prev_chapter()),
                        ft.IconButton(icon=ICONS.ARROW_FORWARD, tooltip="下一章", on_click=lambda _: self.next_chapter()),
                    ]
                ),
                self.reader_scroll,
            ],
        )
        self.content = ft.Container(expand=True, padding=12, content=self.bookshelf_view)
        self.nav = ft.NavigationBar(
            selected_index=0,
            on_change=self.on_nav_change,
            destinations=[
                ft.NavigationBarDestination(icon=ICONS.MENU_BOOK, label="书架"),
                ft.NavigationBarDestination(icon=ICONS.SEARCH, label="搜索"),
                ft.NavigationBarDestination(icon=ICONS.AUTO_STORIES, label="阅读"),
            ],
        )

    def build(self) -> None:
        self.page.title = "Novel Reader"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 0
        self.page.add(ft.Column(expand=True, controls=[self.content, self.status, self.nav]))
        self.load_books()

    def set_status(self, message: str = "", is_error: bool = False) -> None:
        self.status.value = message
        self.status.color = COLORS.RED_700 if is_error else COLORS.BLUE_GREY_600
        self.page.update()

    def show_view(self, index: int) -> None:
        self.nav.selected_index = index
        self.content.content = [self.bookshelf_view, self.search_view, self.reader_view][index]
        self.page.update()

    def on_nav_change(self, event: ft.ControlEvent) -> None:
        self.show_view(int(event.control.selected_index))

    def load_books(self) -> None:
        resp = BookService.list_books()
        if not resp.get("ok"):
            self.set_status(f"加载书架失败：{resp.get('error')}", True)
            return
        self.books = list(resp.get("data") or [])
        self.render_bookshelf()
        self.set_status("")

    def render_bookshelf(self) -> None:
        self.bookshelf_list.controls.clear()
        if not self.books:
            self.bookshelf_list.controls.append(ft.Text("书架为空，请先搜索并添加小说。"))
        for book in self.books:
            subtitle = _author(book)
            if book.get("last_read_chapter"):
                subtitle += f" · 上次读到：{book.get('last_read_chapter')}"
            self.bookshelf_list.controls.append(
                ft.ListTile(
                    title=ft.Text(_title(book)),
                    subtitle=ft.Text(subtitle),
                    on_click=lambda _, b=book: self.open_book(b),
                )
            )
        self.page.update()

    def search(self) -> None:
        keyword = self.search_input.value.strip()
        if not keyword:
            self.set_status("请输入搜索关键词。", True)
            return
        if self.searching:
            self.set_status("正在搜索，请稍候...")
            return
        self.searching = True
        self.search_list.controls.clear()
        self.search_list.controls.append(ft.ProgressRing())
        self.page.update()
        self.set_status("正在通过 Yandex 查找小说网站，并在站内搜索...")
        runner = getattr(self.page, "run_thread", None)
        if callable(runner):
            runner(self._search_worker, keyword)
        else:
            threading.Thread(target=self._search_worker, args=(keyword,), daemon=True).start()

    def _search_worker(self, keyword: str) -> None:
        try:
            resp = CrawlerService.search(keyword)
            if not resp.get("ok"):
                self.search_results = []
                self._show_search_result_status(f"搜索失败：{resp.get('error')}", True)
                return
            self.search_results = list(resp.get("data") or [])
            self._show_search_result_status(f"搜索完成，共 {len(self.search_results)} 条结果。")
        except Exception as e:
            logger.exception("search failed")
            self.search_results = []
            self._show_search_result_status(f"搜索异常：{e}", True)
        finally:
            self.searching = False

    def _show_search_result_status(self, message: str, is_error: bool = False) -> None:
        self.render_search_results()
        self.status.value = message
        self.status.color = COLORS.RED_700 if is_error else COLORS.BLUE_GREY_600
        self.page.update()

    def render_search_results(self) -> None:
        self.search_list.controls.clear()
        if not self.search_results:
            self.search_list.controls.append(ft.Text("没有搜索结果。"))
        for item in self.search_results:
            self.search_list.controls.append(
                ft.ListTile(
                    title=ft.Text(_title(item)),
                    subtitle=ft.Text(f"来源：{_author(item)} · {_url(item)}"),
                    trailing=ft.Icon(ICONS.ADD),
                    on_click=lambda _, result=item: self.add_and_open(result),
                )
            )
        self.page.update()

    def add_and_open(self, result: dict[str, Any]) -> None:
        book_url = _url(result)
        if not book_url:
            self.set_status("搜索结果缺少书籍地址，无法添加。", True)
            return
        self.set_status("正在验证书籍章节目录...")
        chapter_resp = CrawlerService.fetch_chapter_list(book_url)
        chapters = list(chapter_resp.get("data") or []) if chapter_resp.get("ok") else []
        if not chapters:
            self.set_status("这个结果不是可阅读的书籍详情页，已跳过。", True)
            return
        book_info = {
            "title": _title(result),
            "author": _author(result),
            "source_url": book_url,
            "cover_url": result.get("cover_url") or result.get("cover") or "",
        }
        resp = BookService.add_book(book_info)
        if not resp.get("ok"):
            self.set_status(f"添加书籍失败：{resp.get('error')}", True)
            return
        book_id = (resp.get("data") or {}).get("book_id")
        self.load_books()
        book = next((b for b in self.books if b.get("id") == book_id), book_info | {"id": book_id})
        self.current_chapters = chapters
        self.open_book(book)

    def open_book(self, book: dict[str, Any]) -> None:
        self.current_book = dict(book)
        self.current_chapter_index = max(1, int(book.get("last_read_index") or 1))
        self.show_view(2)
        self.load_reader()

    def load_reader(self) -> None:
        if not self.current_book:
            return
        book_id = int(self.current_book.get("id") or 0)
        if not book_id:
            self.set_status("书籍 ID 无效。", True)
            return
        self.current_chapters = self._get_chapters(book_id)
        chapter = self._get_or_fetch_chapter(book_id, self.current_chapter_index)
        if not chapter and self.current_chapters:
            first = self.current_chapters[0]
            self.current_chapter_index = int(first.get("chapter_index") or first.get("index") or 1)
            chapter = self._get_or_fetch_chapter(book_id, self.current_chapter_index)
        if not chapter:
            self.reader_title.value = _title(self.current_book)
            self.reader_body.value = "暂无可阅读章节。"
            self.page.update()
            return
        meta_index = chapter.get("chapter_index") or chapter.get("index")
        if meta_index is not None:
            self.current_chapter_index = int(meta_index)
        self.reader_title.value = str(chapter.get("title") or f"第 {self.current_chapter_index} 章")
        self.reader_body.value = str(chapter.get("content") or "")
        BookService.update_read_progress(book_id, self.current_chapter_index, self.reader_title.value)
        self.set_status("")

    def _get_chapters(self, book_id: int) -> list[dict[str, Any]]:
        resp = ChapterService.list_chapters(book_id)
        chapters = list(resp.get("data") or []) if resp.get("ok") else []
        if chapters or not self.current_book:
            return chapters
        book_url = _url(self.current_book)
        if not book_url:
            return []
        chapter_resp = CrawlerService.fetch_chapter_list(book_url)
        return list(chapter_resp.get("data") or []) if chapter_resp.get("ok") else []

    def _get_or_fetch_chapter(self, book_id: int, index: int) -> dict[str, Any] | None:
        local = ChapterService.get_chapter(book_id, index)
        if local.get("ok") and local.get("data"):
            return dict(local["data"])
        chapter_meta = self._chapter_meta(index)
        chapter_url = str(chapter_meta.get("url") or "")
        if not chapter_url:
            return None
        fetched = CrawlerService.fetch_chapter(chapter_url)
        saved = ChapterService.store_fetched_chapter(book_id, index, chapter_url, fetched)
        if saved.get("ok"):
            local = ChapterService.get_chapter(book_id, index)
            if local.get("ok") and local.get("data"):
                return dict(local["data"])
        return fetched.get("data") if fetched.get("ok") else None

    def _chapter_meta(self, index: int) -> dict[str, Any]:
        for chapter in self.current_chapters:
            chapter_index = chapter.get("chapter_index", chapter.get("index", 0))
            if int(chapter_index or 0) == index:
                return dict(chapter)
        if self.current_chapters and 0 <= index < len(self.current_chapters):
            return dict(self.current_chapters[index])
        return {}

    def prev_chapter(self) -> None:
        if self.current_chapter_index <= 1:
            self.set_status("已经是第一章。")
            return
        self.current_chapter_index -= 1
        self.load_reader()

    def next_chapter(self) -> None:
        self.current_chapter_index += 1
        self.load_reader()


def main(page: ft.Page) -> None:
    FletNovelReader(page).build()


if __name__ == "__main__":
    ft.app(target=main)
