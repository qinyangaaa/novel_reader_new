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


if __name__ == "__main__":
    NovelReaderApp().run()
