"""
简易书架 Screen：展示 AppState 中的书籍列表并响应下载完成事件。
"""
from __future__ import annotations

import logging
from functools import partial
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button

from kivy.properties import ListProperty

from .base_screen import BaseScreen
from ..adapters import ui_dispatcher, event_adapter
from ...core import app_state
from ...services.book_service import BookService

logger = logging.getLogger(__name__)


class BookshelfScreen(BaseScreen):
    books = ListProperty([])

    def __init__(self, **kw):
        super().__init__(**kw)
        self._build_ui()

    def _build_ui(self):
        self.root = BoxLayout(orientation='vertical', spacing=8, padding=8)
        self.header = BoxLayout(size_hint_y=None, height='40dp', spacing=8)
        self.lbl = Label(text='书架', halign='left', valign='middle')
        self.lbl.bind(size=lambda *_: setattr(self.lbl, "text_size", self.lbl.size))
        self.search_btn = Button(text='搜索', size_hint_x=None, width='88dp')
        self.search_btn.bind(on_press=lambda *_: self._go_search())
        self.header.add_widget(self.lbl)
        self.header.add_widget(self.search_btn)
        self.root.add_widget(self.header)
        self.status = Label(text='加载中...', size_hint_y=None, height='28dp', halign='left', valign='middle')
        self.status.bind(size=lambda *_: setattr(self.status, "text_size", self.status.size))
        self.root.add_widget(self.status)
        self.error = Label(text='', size_hint_y=None, height='26dp', halign='left', valign='middle', color=(0.82, 0.2, 0.2, 1))
        self.error.bind(size=lambda *_: setattr(self.error, "text_size", self.error.size))
        self.root.add_widget(self.error)
        self.content = BoxLayout(orientation='vertical')
        self.root.add_widget(self.content)
        self.add_widget(self.root)

    def on_app_state(self, state):
        current_book = state.get('current_book') if isinstance(state, dict) else None
        if current_book:
            self.status.text = f"最近阅读：{current_book.get('title', '未知')}"
        self.refresh()

    def on_downloads(self, state):
        # 简单响应：打印日志并刷新 UI
        def _log(dt):
            logger.info('BookshelfScreen received downloads update: %s', state)
            # 可以触发局部刷新
            ui_dispatcher.safe_refresh(self)

        ui_dispatcher.run_on_ui_thread(_log)

    def on_enter(self, *args):
        super().on_enter(*args)
        # 额外绑定 download.completed 事件
        self._download_token = event_adapter.bind_event('download.completed', self._on_download_completed, screen=self)
        self.refresh()

    def on_pre_leave(self, *args):
        # 自动解绑由 BaseScreen 和 adapter 处理
        try:
            event_adapter.unbind_event(self._download_token)
        except Exception:
            pass
        super().on_pre_leave(*args)

    def _on_download_completed(self, payload):
        # payload 包含 task and result
        logger.info('下载完成事件: %s', payload)
        ui_dispatcher.safe_refresh(self)

    def refresh(self):
        ui_dispatcher.run_in_background(BookService.list_books, on_done=self._on_books_loaded)

    def _on_books_loaded(self, result):
        if isinstance(result, Exception) or not result.get("ok"):
            self.status.text = "书架加载失败"
            self.error.text = "本地数据读取失败"
            return
        self.error.text = ""
        self.books = result.get("data") or []
        self.content.clear_widgets()
        if not self.books:
            self.content.add_widget(Label(text='书架为空'))
            self.status.text = "暂无书籍"
            return
        self.status.text = f"共 {len(self.books)} 本"
        for book in self.books:
            row = BoxLayout(size_hint_y=None, height='44dp', spacing=8)
            title = book.get('title', '未知')
            chapter = book.get('last_read_chapter') or '未开始'
            btn = Button(text=title, halign='left')
            btn.bind(on_press=partial(self._open_book, dict(book)))
            meta = Label(text=chapter, size_hint_x=0.35, halign='left', valign='middle')
            meta.bind(size=lambda inst, *_: setattr(inst, "text_size", inst.size))
            row.add_widget(btn)
            row.add_widget(meta)
            self.content.add_widget(row)

    def _open_book(self, book: dict, *_args):
        logger.info("BookshelfScreen open book: %s", book.get("title"))
        app_state.update_current_book(book)
        if self.manager is not None and self.manager.has_screen("reader"):
            self.manager.current = "reader"

    def _go_search(self):
        if self.manager is not None and self.manager.has_screen("search"):
            self.manager.current = "search"
