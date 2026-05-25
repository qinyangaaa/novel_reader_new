"""
Crawler 注册表与共享 Session 管理。

功能：register/unregister/get_crawler_by_url/get_available_crawlers
维护每个爬虫的可用性与失败次数，用于自动失效切换。
"""
from __future__ import annotations

import time
import threading
from typing import Dict, List, Optional, Type

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base_crawler import BaseCrawler

# 注册表结构：name -> {'instance': BaseCrawler, 'meta': {...}}
_registry: Dict[str, Dict] = {}
_lock = threading.RLock()

# 共享 session 初始化
_session: Optional[requests.Session] = None


def get_session() -> requests.Session:
    """返回配置好的 requests.Session（重试、超时、UA）。"""
    global _session
    if _session is None:
        s = requests.Session()
        retries = Retry(total=2, backoff_factor=0.3, status_forcelist=(500, 502, 503, 504))
        adapter = HTTPAdapter(max_retries=retries, pool_maxsize=10)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        # 浏览器 UA，兼容移动端
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Mobile Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        _session = s
    return _session


def register(crawler: BaseCrawler, priority: int = 100, cooldown: int = 300) -> None:
    """注册 crawler 实例，并设置优先级与失效冷却（秒）。"""
    with _lock:
        _registry[crawler.name] = {
            "instance": crawler,
            "priority": int(priority),
            "cooldown": int(cooldown),
            "failed_at": 0.0,
            "failure_count": 0,
            "disabled": False,
        }


def unregister(name: str) -> None:
    with _lock:
        if name in _registry:
            del _registry[name]


def _is_available(meta: Dict) -> bool:
    # 如果被显式禁用，则不可用
    if meta.get("disabled"):
        return False
    # 如果处于冷却期，则不可用
    failed_at = meta.get("failed_at", 0)
    cooldown = meta.get("cooldown", 300)
    if failed_at and (time.time() - failed_at) < cooldown:
        return False
    return True


def get_available_crawlers() -> List[BaseCrawler]:
    """返回当前可用 crawler 实例，按 priority 升序（数值小优先）。"""
    with _lock:
        items = [m for m in _registry.values() if _is_available(m)]
        items.sort(key=lambda x: x.get("priority", 100))
        return [i["instance"] for i in items]


def get_crawler_by_url(url: str) -> List[BaseCrawler]:
    """根据 url 返回可用的 crawler 列表（按优先级）。

    匹配规则：若 crawler.supported_domains 包含 url 的域名则匹配；否则返回可用的 crawlers（兜底）。
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    domain = parsed.netloc
    matches: List[BaseCrawler] = []
    with _lock:
        for meta in _registry.values():
            inst: BaseCrawler = meta["instance"]
            supported = getattr(inst, "supported_domains", None) or []
            if any(d for d in supported if d in domain):
                if _is_available(meta):
                    matches.append(inst)
        # 如果未找到特定匹配，返回所有可用 crawler（用于 fallback），按优先级
        if not matches:
            matches = get_available_crawlers()
    return matches


def mark_failure(name: str) -> None:
    """标记某个 crawler 失败：增加失败计数并设置 failed_at。如果失败次数超过阈值可选择禁用。

    目前策略：failure_count 增到 3 时记录 failed_at，进入 cooldown。
    """
    with _lock:
        meta = _registry.get(name)
        if not meta:
            return
        meta["failure_count"] = meta.get("failure_count", 0) + 1
        if meta["failure_count"] >= 3:
            meta["failed_at"] = time.time()
            meta["failure_count"] = 0


def mark_success(name: str) -> None:
    """重置失败计数并清除 failed_at。"""
    with _lock:
        meta = _registry.get(name)
        if not meta:
            return
        meta["failure_count"] = 0
        meta["failed_at"] = 0.0
