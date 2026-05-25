"""
BaseScreen：自动绑定/解绑 AppState，并提供生命周期日志。
"""
from __future__ import annotations

import logging
from kivy.uix.screenmanager import Screen

from ..adapters import screen_state_binding, event_adapter

logger = logging.getLogger(__name__)


class BaseScreen(Screen):
    def on_enter(self, *args):
        logger.info("%s on_enter", self.__class__.__name__)
        # 绑定并同步状态
        screen_state_binding.bind_screen(self, sync_on_bind=True)
        return super().on_enter(*args)

    def on_pre_leave(self, *args):
        logger.info("%s on_pre_leave", self.__class__.__name__)
        # 主动解绑
        screen_state_binding.unbind_screen(self)
        return super().on_pre_leave(*args)

    def on_leave(self, *args):
        logger.info("%s on_leave", self.__class__.__name__)
        screen_state_binding.unbind_screen(self)
        return super().on_leave(*args)

    def on_destroy(self):
        # 当 Screen 被销毁时清理
        event_adapter.auto_cleanup(self)
