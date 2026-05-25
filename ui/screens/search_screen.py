"""
搜索 Screen：通过 UI 触发服务层搜索，演示后台执行与 UI 回调。
"""
from __future__ import annotations

import logging
from functools import partial
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

from .base_screen import BaseScreen
from ..adapters import ui_dispatcher
from ...core import app_state
from ...services.book_service import BookService
from ...services.crawler_service import CrawlerService

logger = logging.getLogger(__name__)


class SearchScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._build_ui()

    def _build_ui(self):
        self.layout = BoxLayout(orientation='vertical', spacing=8, padding=8)
        self.header = BoxLayout(size_hint_y=None, height='40dp', spacing=8)
        self.back_btn = Button(text='书架', size_hint_x=None, width='88dp')
        self.back_btn.bind(on_press=lambda *_: self._go_bookshelf())
        self.input = TextInput(hint_text='搜索书名', size_hint_y=None, height='40dp')
        self.btn = Button(text='搜索', size_hint_x=None, width='88dp')
        self.btn.bind(on_press=self.on_search_pressed)
        self.header.add_widget(self.back_btn)
        self.header.add_widget(self.input)
        self.header.add_widget(self.btn)
        self.result_label = Label(text='结果：', size_hint_y=None, height='30dp', halign='left', valign='middle')
        self.result_label.bind(size=lambda *_: setattr(self.result_label, "text_size", self.result_label.size))
        self.error_label = Label(text='', size_hint_y=None, height='26dp', halign='left', valign='middle', color=(0.82, 0.2, 0.2, 1))
        self.error_label.bind(size=lambda *_: setattr(self.error_label, "text_size", self.error_label.size))
        self.results = BoxLayout(orientation='vertical', spacing=6)
        self.layout.add_widget(self.header)
        self.layout.add_widget(self.result_label)
        self.layout.add_widget(self.error_label)
        self.layout.add_widget(self.results)
        self.add_widget(self.layout)

    def on_search_pressed(self, *args):
        kw = self.input.text.strip()
        if not kw:
            self._set_error("请输入书名")
            return
        self._set_error("")
        self.result_label.text = "搜索中..."

        # 在后台执行搜索，结果回到 UI 线程
        def _do_search():
            try:
                resp = CrawlerService.search(kw)
                return resp
            except Exception as e:
                return {"ok": False, "error": str(e)}

        def _on_done(res):
            # res 在 UI 线程
            if isinstance(res, Exception):
                self.result_label.text = f'错误: {res}'
                self._set_error("搜索请求失败")
            else:
                if res.get('ok'):
                    data = res.get('data') or []
                    self.result_label.text = f'找到 {len(data)} 条结果'
                    self._set_error("" if data else "未找到匹配结果")
                    self._render_results(data)
                else:
                    self.result_label.text = f'搜索失败: {res.get("error")}'
                    self._set_error("网络异常或站点不可用")
                    self._render_results([])

        ui_dispatcher.run_in_background(_do_search, on_done=_on_done)

    def _render_results(self, rows):
        self.results.clear_widgets()
        if not rows:
            self.results.add_widget(Label(text='暂无结果'))
            return
        for row in rows[:12]:
            title = row.get("title") or row.get("name") or "未知书籍"
            source_url = row.get("url") or row.get("source_url") or row.get("book_url")
            line = BoxLayout(size_hint_y=None, height='44dp', spacing=8)
            btn = Button(text=title)
            btn.bind(on_press=partial(self._open_result, dict(row)))
            meta = Label(text=(row.get("author") or source_url or "")[:48], size_hint_x=0.42, halign='left', valign='middle')
            meta.bind(size=lambda inst, *_: setattr(inst, "text_size", inst.size))
            line.add_widget(btn)
            line.add_widget(meta)
            self.results.add_widget(line)

    def _open_result(self, row: dict, *_args):
        self.result_label.text = f"打开：{row.get('title', '未知')}"
        self._set_error("")

        def _prepare():
            source_url = row.get("url") or row.get("source_url") or row.get("book_url")
            if not source_url:
                return {"ok": False, "error": "source_url_missing"}
            add_resp = BookService.add_book(
                {
                    "title": row.get("title") or "未知书籍",
                    "author": row.get("author", ""),
                    "source_url": source_url,
                    "cover_url": row.get("cover_url", ""),
                }
            )
            if not add_resp.get("ok") or not add_resp.get("data"):
                return {"ok": False, "error": add_resp.get("error") or "add_book_failed"}
            book_id = int(add_resp["data"]["book_id"])
            book_resp = BookService.get_book(book_id)
            if not book_resp.get("ok"):
                return {"ok": False, "error": book_resp.get("error") or "book_not_found"}
            chapter_resp = CrawlerService.fetch_chapter_list(source_url)
            chapters = chapter_resp.get("data") if chapter_resp.get("ok") else []
            book = dict(book_resp["data"])
            book["chapters"] = chapters or []
            return {"ok": True, "data": book}

        def _on_done(res):
            if isinstance(res, Exception) or not res.get("ok"):
                self.result_label.text = f"打开失败: {getattr(res, 'args', [res])[0] if isinstance(res, Exception) else res.get('error')}"
                self._set_error("书籍信息加载失败")
                return
            book = res["data"]
            logger.info("SearchScreen open reader: %s", book.get("title"))
            app_state.update_current_book(book)
            if self.manager is not None and self.manager.has_screen("reader"):
                self.manager.current = "reader"

        ui_dispatcher.run_in_background(_prepare, on_done=_on_done)

    def _go_bookshelf(self):
        if self.manager is not None and self.manager.has_screen("bookshelf"):
            self.manager.current = "bookshelf"

    def _set_error(self, message: str):
        self.error_label.text = message
