"""
ReaderScreen: stable-first reading UI for MVP readable state.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget

from .base_screen import BaseScreen
from ..adapters import event_adapter, ui_dispatcher
from ...core import app_state
from ...services.book_service import BookService
from ...services.chapter_service import ChapterService
from ...services.crawler_service import CrawlerService
from ...services.download_manager import DownloadManager

logger = logging.getLogger(__name__)


class TapZone(Widget):
    def __init__(self, on_tap, **kwargs):
        super().__init__(**kwargs)
        self._on_tap = on_tap
        self._touch_start = None

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._touch_start = touch.pos
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            moved = False
            if self._touch_start is not None:
                moved = abs(touch.pos[0] - self._touch_start[0]) > 12 or abs(touch.pos[1] - self._touch_start[1]) > 12
            self._touch_start = None
            if callable(self._on_tap) and not moved:
                self._on_tap()
                return True
        return super().on_touch_up(touch)


class ReaderScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.book: Dict = {}
        self.chapter_list: List[Dict] = []
        self.current_index = 0
        self.controls_visible = True
        self.download_manager = DownloadManager(max_workers=2)
        self._theme = "light"
        self._font_size = 18
        self._download_token = None
        self._download_failed_token = None
        self._chapter_text = "请选择书籍后进入阅读页"
        self._rendered_text = None
        self._rendered_font_size = None
        self._rendered_theme = None
        self._preload_window = 3
        self._content_trigger = Clock.create_trigger(self._apply_content_render, 0)
        self._appearance_trigger = Clock.create_trigger(self._apply_appearance_render, 0)
        self._build_ui()

    def _build_ui(self):
        self.root = FloatLayout()
        with self.root.canvas.before:
            self._bg_color = Color(0.97, 0.95, 0.9, 1)
            self._bg_rect = Rectangle(pos=self.root.pos, size=self.root.size)
        self.root.bind(pos=self._sync_bg, size=self._sync_bg)

        self.content_wrap = BoxLayout(orientation="vertical", padding=[22, 18, 22, 18])
        self.scroll = ScrollView(
            size_hint=(1, 1),
            do_scroll_x=False,
            bar_width="6dp",
        )
        self.text_label = Label(
            text=self._chapter_text,
            markup=False,
            halign="left",
            valign="top",
            size_hint_y=None,
        )
        self.text_label.bind(width=self._sync_text_width, texture_size=self._sync_text_height)
        self.scroll.add_widget(self.text_label)
        self.content_wrap.add_widget(self.scroll)
        self.root.add_widget(self.content_wrap)

        self.tap_zone = TapZone(on_tap=self.toggle_controls)
        self.root.add_widget(self.tap_zone)

        self.control_bar = BoxLayout(
            orientation="vertical",
            spacing=8,
            padding=[12, 10, 12, 10],
            size_hint=(1, None),
            height="124dp",
            pos_hint={"top": 1},
        )
        with self.control_bar.canvas.before:
            self._control_bg = Color(1, 1, 1, 0.96)
            self._control_rect = Rectangle(pos=self.control_bar.pos, size=self.control_bar.size)
        self.control_bar.bind(pos=self._sync_control_bg, size=self._sync_control_bg)

        self.header_row = BoxLayout(size_hint_y=None, height="34dp", spacing=8)
        self.back_btn = Button(text="书架", size_hint_x=None, width="72dp")
        self.back_btn.bind(on_press=self.go_bookshelf)
        self.title_label = Label(text="Reader", halign="left", valign="middle")
        self.title_label.bind(size=self._sync_title_text)
        self.theme_btn = Button(text="夜间", size_hint_x=None, width="72dp")
        self.theme_btn.bind(on_press=self.toggle_theme)
        self.header_row.add_widget(self.back_btn)
        self.header_row.add_widget(self.title_label)
        self.header_row.add_widget(self.theme_btn)
        self.control_bar.add_widget(self.header_row)

        self.slider_row = BoxLayout(size_hint_y=None, height="34dp", spacing=8)
        self.font_label = Label(text="字体 18", size_hint_x=None, width="72dp")
        self.font_slider = Slider(min=14, max=30, value=self._font_size)
        self.font_slider.bind(value=self.on_font_size_change)
        self.slider_row.add_widget(self.font_label)
        self.slider_row.add_widget(self.font_slider)
        self.control_bar.add_widget(self.slider_row)

        self.nav_row = BoxLayout(size_hint_y=None, height="38dp", spacing=8)
        self.prev_btn = Button(text="上一章")
        self.prev_btn.bind(on_press=self.go_prev)
        self.chapter_label = Label(text="未加载", halign="center", valign="middle")
        self.chapter_label.bind(size=self._sync_chapter_text)
        self.next_btn = Button(text="下一章")
        self.next_btn.bind(on_press=self.go_next)
        self.nav_row.add_widget(self.prev_btn)
        self.nav_row.add_widget(self.chapter_label)
        self.nav_row.add_widget(self.next_btn)
        self.control_bar.add_widget(self.nav_row)
        self.root.add_widget(self.control_bar)

        self.status_bar = Label(
            text="就绪",
            size_hint=(1, None),
            height="30dp",
            pos_hint={"x": 0, "y": 0},
            halign="left",
            valign="middle",
        )
        self.status_bar.bind(size=self._sync_status_text)
        self.root.add_widget(self.status_bar)
        self.error_bar = Label(
            text="",
            size_hint=(1, None),
            height="28dp",
            pos_hint={"x": 0, "y": 0.045},
            halign="left",
            valign="middle",
            color=(0.82, 0.24, 0.24, 1),
        )
        self.error_bar.bind(size=lambda *_: setattr(self.error_bar, "text_size", self.error_bar.size))
        self.root.add_widget(self.error_bar)

        self.add_widget(self.root)
        self._schedule_render(full=True)

    def _sync_bg(self, *_args):
        self._bg_rect.pos = self.root.pos
        self._bg_rect.size = self.root.size
        self.tap_zone.pos = self.root.pos
        self.tap_zone.size = self.root.size

    def _sync_control_bg(self, *_args):
        self._control_rect.pos = self.control_bar.pos
        self._control_rect.size = self.control_bar.size

    def _sync_text_width(self, *_args):
        self.text_label.text_size = (self.scroll.width - 32, None)

    def _sync_text_height(self, *_args):
        self.text_label.height = max(self.text_label.texture_size[1] + 24, self.scroll.height)

    def _sync_title_text(self, *_args):
        self.title_label.text_size = self.title_label.size

    def _sync_chapter_text(self, *_args):
        self.chapter_label.text_size = self.chapter_label.size

    def _sync_status_text(self, *_args):
        self.status_bar.text_size = self.status_bar.size

    def _schedule_render(self, full: bool = False):
        if full:
            self._rendered_text = None
            self._rendered_font_size = None
            self._rendered_theme = None
            self._content_trigger()
            self._appearance_trigger()
            return
        self._content_trigger()
        self._appearance_trigger()

    def _apply_content_render(self, _dt):
        font_changed = self._rendered_font_size != self._font_size
        text_changed = self._rendered_text != self._chapter_text
        if text_changed:
            self.text_label.text = self._chapter_text
            self._rendered_text = self._chapter_text
        if font_changed:
            self.text_label.font_size = f"{self._font_size}sp"
            self.font_label.text = f"字体 {self._font_size}"
            self._rendered_font_size = self._font_size
        if text_changed or font_changed:
            self._sync_text_width()
            self._sync_text_height()

    def _apply_appearance_render(self, _dt):
        if self._rendered_theme == self._theme and self._rendered_font_size == self._font_size:
            return
        self._apply_theme()
        self._rendered_theme = self._theme

    def on_enter(self, *args):
        super().on_enter(*args)
        self._download_token = event_adapter.bind_event("download.completed", self._on_download_completed, screen=self)
        self._download_failed_token = event_adapter.bind_event("download.failed", self._on_download_failed, screen=self)
        event_adapter.bind_event("app.reading_theme", self._on_theme_event, screen=self)
        event_adapter.bind_event("app.font_size", self._on_font_size_event, screen=self)
        ui_dispatcher.run_in_background(self._prepare_reader_context, on_done=self._on_reader_context_ready)

    def on_pre_leave(self, *args):
        if self._download_token:
            event_adapter.unbind_event(self._download_token)
            self._download_token = None
        if self._download_failed_token:
            event_adapter.unbind_event(self._download_failed_token)
            self._download_failed_token = None
        super().on_pre_leave(*args)

    def on_app_state(self, state):
        if isinstance(state, dict) and state.get("id"):
            self.book = dict(state)

    def _prepare_reader_context(self):
        state_book = app_state.get_state().current_book or {}
        if not state_book or not state_book.get("id"):
            return {"ok": False, "error": "no_current_book"}

        book_resp = BookService.get_book(int(state_book["id"]))
        book = dict(state_book)
        if book_resp.get("ok") and book_resp.get("data"):
            book.update(book_resp["data"])

        local_resp = ChapterService.list_chapters(int(book["id"]))
        local_chapters = local_resp.get("data") or []
        chapter_list = self._normalize_chapter_list(book, local_chapters)
        if not chapter_list and isinstance(state_book.get("chapters"), list):
            chapter_list = self._normalize_chapter_list(book, state_book["chapters"])
        if not chapter_list and book.get("source_url"):
            remote_resp = CrawlerService.fetch_chapter_list(book["source_url"])
            if remote_resp.get("ok") and remote_resp.get("data"):
                chapter_list = self._normalize_chapter_list(book, remote_resp["data"])
        return {"ok": True, "book": book, "chapters": chapter_list}

    def _on_reader_context_ready(self, result):
        if isinstance(result, Exception) or not result.get("ok"):
            self._set_error("阅读上下文加载失败")
            self._set_status(f"加载失败: {getattr(result, 'args', [result])[0] if isinstance(result, Exception) else result.get('error')}")
            return
        self.book = result["book"]
        self.chapter_list = result["chapters"]
        self.title_label.text = self.book.get("title", "Reader")
        self._theme = app_state.get_state().reading_theme
        self._font_size = app_state.get_state().font_size
        self._schedule_render(full=True)
        start_index = int(self.book.get("last_read_index", 0) or 0)
        if self.chapter_list:
            start_index = max(0, min(start_index, len(self.chapter_list) - 1))
        self.load_chapter(start_index)

    def _normalize_chapter_list(self, book: Dict, rows: List[Dict]) -> List[Dict]:
        normalized = []
        for idx, row in enumerate(rows):
            chapter_index = int(row.get("chapter_index", idx))
            normalized.append(
                {
                    "title": row.get("title") or f"第{chapter_index + 1}章",
                    "url": row.get("url"),
                    "chapter_index": chapter_index,
                    "is_downloaded": int(row.get("is_downloaded", 0)),
                    "book_id": int(book["id"]),
                }
            )
        normalized.sort(key=lambda item: item["chapter_index"])
        return normalized

    def load_chapter(self, chapter_index: int):
        if not self.book or not self.book.get("id"):
            self._set_error("没有当前书籍")
            self._set_status("未选择书籍")
            return
        if not self.chapter_list:
            self._set_error("章节列表不可用")
            self._set_status("没有可读章节")
            return
        chapter_index = max(0, min(chapter_index, len(self.chapter_list) - 1))
        meta = self.chapter_list[chapter_index]
        self.current_index = chapter_index
        self.chapter_label.text = meta.get("title", "未命名章节")
        self._set_status("加载章节中...")
        ui_dispatcher.run_in_background(
            lambda: self._load_or_fetch_chapter(meta),
            on_done=self._on_chapter_loaded,
        )

    def _load_or_fetch_chapter(self, meta: Dict):
        book_id = int(self.book["id"])
        chapter_index = int(meta["chapter_index"])
        local = ChapterService.get_chapter(book_id, chapter_index)
        if local.get("ok") and local.get("data") and local["data"].get("content"):
            return {"ok": True, "data": local["data"], "source": "local"}
        url = meta.get("url")
        if not url:
            return {"ok": False, "error": "chapter_url_missing", "meta": meta}
        cached = ChapterService.get_cached_by_url(url)
        if cached and cached.get("content"):
            return {"ok": True, "data": cached, "source": "memory"}
        remote = CrawlerService.fetch_chapter(url)
        if not remote.get("ok"):
            return {"ok": False, "error": remote.get("error") or "fetch_failed", "meta": meta}
        stored = ChapterService.store_fetched_chapter(book_id, chapter_index, url, remote)
        if not stored.get("ok"):
            return {"ok": False, "error": stored.get("error") or "save_failed", "meta": meta}
        saved = ChapterService.get_chapter(book_id, chapter_index)
        if saved.get("ok"):
            return {"ok": True, "data": saved["data"], "source": "remote"}
        return {"ok": False, "error": "chapter_not_saved", "meta": meta}

    def _on_chapter_loaded(self, result):
        if isinstance(result, Exception) or not result.get("ok"):
            error = getattr(result, "args", [result])[0] if isinstance(result, Exception) else result.get("error")
            self._chapter_text = f"章节加载失败\n\n{error}"
            self._content_trigger()
            self._set_error("网络失败或章节抓取失败")
            self._set_status(f"加载失败: {error}")
            return
        chapter = result["data"]
        self._chapter_text = chapter.get("content") or "本章内容为空"
        self._content_trigger()
        self._set_error("")
        self.chapter_label.text = chapter.get("title") or self.chapter_label.text
        self.scroll.scroll_y = 1
        self._set_status(f"已加载: {result.get('source', 'local')}")
        self._save_progress(chapter)
        self._preload_next_chapters()

    def _save_progress(self, chapter: Dict):
        chapter_title = chapter.get("title") or self.chapter_label.text
        chapter_index = int(chapter.get("chapter_index", self.current_index))
        if self.book.get("id"):
            ui_dispatcher.run_in_background(
                lambda: BookService.update_read_progress(int(self.book["id"]), chapter_index, chapter_title)
            )
        self.book["last_read_index"] = chapter_index
        self.book["last_read_chapter"] = chapter_title
        self.book["reading_theme"] = self._theme
        self.book["font_size"] = self._font_size
        app_state.update_current_book(dict(self.book))
        app_state.update_current_chapter(
            {
                "book_id": self.book.get("id"),
                "chapter_index": chapter_index,
                "title": chapter_title,
            }
        )

    def _preload_next_chapters(self):
        urls = []
        active_urls = set(self.download_manager.get_active_urls())
        for offset in range(1, self._preload_window + 1):
            next_pos = self.current_index + offset
            if next_pos >= len(self.chapter_list):
                break
            meta = self.chapter_list[next_pos]
            url = meta.get("url")
            if not url:
                continue
            if meta.get("is_downloaded") or ChapterService.has_local_chapter(int(self.book["id"]), int(meta["chapter_index"])):
                meta["is_downloaded"] = 1
                continue
            if ChapterService.get_cached_by_url(url):
                meta["is_downloaded"] = 1
                continue
            if url in active_urls or url in urls:
                continue
            urls.append(url)
        if not urls:
            self._set_status("后续章节已就绪")
            return
        self.download_manager.preload_chapters(urls, callback=self._on_preload_finished)
        self._set_status(f"后台预加载 {len(urls)} 章")

    def _on_preload_finished(self, task: Dict):
        result = task.get("result") or {}
        url = task.get("url")
        if not result.get("ok") or not url:
            return
        for meta in self.chapter_list:
            if meta.get("url") == url:
                ChapterService.store_fetched_chapter(
                    int(self.book["id"]),
                    int(meta["chapter_index"]),
                    url,
                    result,
                )
                meta["is_downloaded"] = 1
                break

    def _on_download_completed(self, payload):
        task = payload.get("task", {})
        self._set_error("")
        self._set_status(f"预加载完成: {task.get('id', '')[:8]}")

    def _on_download_failed(self, payload):
        task = payload.get("task", {})
        result = payload.get("result", {})
        error = result.get("error") or task.get("status") or "unknown"
        self._set_error("后续章节预加载失败")
        self._set_status(f"下载失败: {error}")

    def go_prev(self, *_args):
        if self.current_index > 0:
            self.load_chapter(self.current_index - 1)

    def go_next(self, *_args):
        if self.current_index + 1 < len(self.chapter_list):
            self.load_chapter(self.current_index + 1)

    def go_bookshelf(self, *_args):
        if self.manager is not None and self.manager.has_screen("bookshelf"):
            self.manager.current = "bookshelf"

    def toggle_controls(self, *_args):
        self.controls_visible = not self.controls_visible
        self.control_bar.opacity = 1 if self.controls_visible else 0
        self.control_bar.disabled = not self.controls_visible

    def toggle_theme(self, *_args):
        self._theme = "dark" if self._theme == "light" else "light"
        app_state.set_reading_theme(self._theme)
        self._appearance_trigger()

    def _on_theme_event(self, payload):
        next_theme = payload.get("reading_theme", self._theme)
        if next_theme == self._theme:
            return
        self._theme = next_theme
        self._appearance_trigger()

    def on_font_size_change(self, *_args):
        next_size = int(self.font_slider.value)
        if next_size == self._font_size:
            return
        self._font_size = next_size
        app_state.set_font_size(self._font_size)
        self._content_trigger()

    def _on_font_size_event(self, payload):
        next_size = int(payload.get("font_size", self._font_size))
        if next_size == self._font_size and int(self.font_slider.value) == next_size:
            return
        self._font_size = next_size
        if int(self.font_slider.value) != self._font_size:
            self.font_slider.value = self._font_size
        self._content_trigger()

    def _apply_theme(self):
        if self._theme == "dark":
            self._bg_color.rgba = (0.09, 0.1, 0.12, 1)
            self._control_bg.rgba = (0.14, 0.15, 0.18, 0.96)
            fg = (0.9, 0.9, 0.92, 1)
            self.theme_btn.text = "日间"
        else:
            self._bg_color.rgba = (0.97, 0.95, 0.9, 1)
            self._control_bg.rgba = (1, 1, 1, 0.96)
            fg = (0.12, 0.12, 0.12, 1)
            self.theme_btn.text = "夜间"
        self.text_label.color = fg
        self.title_label.color = fg
        self.chapter_label.color = fg
        self.status_bar.color = fg
        self.font_label.color = fg

    def _set_status(self, text: str):
        self.status_bar.text = text

    def _set_error(self, text: str):
        self.error_bar.text = text
