"""
MVP app entry integrating Bookshelf, Search, and Reader with ScreenManager.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path


def crash_handler(exc_type, exc_value, exc_tb):
    try:
        # 安卓 sdcard
        log_path = Path("/sdcard/novel_reader_error.txt")

        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exception(
                exc_type,
                exc_value,
                exc_tb,
                file=f
            )

    except Exception:
        try:
            # fallback 当前目录
            log_path = Path("novel_reader_error.txt")

            with open(log_path, "w", encoding="utf-8") as f:
                traceback.print_exception(
                    exc_type,
                    exc_value,
                    exc_tb,
                    file=f
                )

        except Exception:
            pass


sys.excepthook = crash_handler



import logging
import os
from pathlib import Path

os.environ.setdefault("KIVY_HOME", str(Path(__file__).resolve().parent / ".kivy"))

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, NoTransition

from novel_reader.core import app_state
from novel_reader.ui.adapters import ui_dispatcher
from novel_reader.ui.screens.bookshelf_screen import BookshelfScreen
from novel_reader.ui.screens.search_screen import SearchScreen
from novel_reader.ui.screens.reader_screen import ReaderScreen
from novel_reader.services.book_service import BookService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


class NovelReaderApp(App):
    def build(self):
        self.title = "Novel Reader"
        self.manager = ScreenManager(transition=NoTransition())
        self.manager.add_widget(BookshelfScreen(name="bookshelf"))
        self.manager.add_widget(SearchScreen(name="search"))
        self.manager.add_widget(ReaderScreen(name="reader"))
        self.manager.bind(current=self._on_screen_changed)
        ui_dispatcher.run_in_background(self._restore_last_reading, on_done=self._on_restore_ready)
        return self.manager

    def _on_screen_changed(self, *_args):
        logger.info("Screen switch -> %s", self.manager.current)

    def _restore_last_reading(self):
        books_resp = BookService.list_books()
        if not books_resp.get("ok"):
            return {"target": "bookshelf", "book": None}
        books = books_resp.get("data") or []
        if not books:
            return {"target": "bookshelf", "book": None}
        candidate = None
        for book in books:
            if book.get("last_read_chapter") or int(book.get("last_read_index", 0) or 0) > 0:
                candidate = book
                break
        if candidate is None:
            candidate = books[0]
        target = "reader" if candidate.get("last_read_chapter") or int(candidate.get("last_read_index", 0) or 0) > 0 else "bookshelf"
        return {"target": target, "book": candidate}

    def _on_restore_ready(self, result):
        if isinstance(result, Exception) or not isinstance(result, dict):
            self.manager.current = "bookshelf"
            return
        book = result.get("book")
        if book:
            app_state.update_current_book(dict(book))
        self.manager.current = result.get("target", "bookshelf")


if __name__ == "__main__":
    NovelReaderApp().run()
