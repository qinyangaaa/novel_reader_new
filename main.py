"""
APK entrypoint for Buildozer / python-for-android.

The repository root is also the Python package root, so we register a
synthetic `novel_reader` package pointing at the current directory before
importing the real app module.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parent

if "novel_reader" not in sys.modules:
    pkg = types.ModuleType("novel_reader")
    pkg.__path__ = [str(ROOT)]
    sys.modules["novel_reader"] = pkg

from novel_reader.app import NovelReaderApp
import traceback
import os


def _write_crash_log(text: str) -> None:
    """尝试把崩溃日志写到外部 SD 卡和当前工作目录（降级）。"""
    paths = ["/sdcard/novel_reader_crash.txt", os.path.join(os.getcwd(), "novel_reader_crash.txt")]
    for p in paths:
        try:
            d = os.path.dirname(p)
            if d and not os.path.exists(d):
                try:
                    os.makedirs(d, exist_ok=True)
                except Exception:
                    pass
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            # 忽略写入错误
            pass


if __name__ == "__main__":
    try:
        NovelReaderApp().run()
    except Exception:
        tb = traceback.format_exc()
        _write_crash_log(tb)
        # 重新抛出以便在调试时看到日志（在 release 可选择退出）
        raise
