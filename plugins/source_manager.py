"""
网站源管理器：搜索、可用性检测与批量更新

功能：
- discover_sources(keyword): 在 Bing 上搜索并提取搜索结果中的网站域名
- health_check(url): 测试网址是否可访问并能被 trafilatura 提取正文
- update_sources(db_path=None): 批量检测数据库中所有网址，更新 is_active、success_rate、last_checked

代码要点：
- 所有网络请求设置浏览器 User-Agent
- 网络请求带异常处理并自动重试（最多 3 次）
- 使用线程池并发检测以加快批量更新

作者：重写版
"""
from __future__ import annotations

import concurrent.futures
import datetime
import logging
import re
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse, urljoin, quote_plus

import requests
import trafilatura

# 默认的浏览器 User-Agent，适用于 Android WebView/移动浏览器场景
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36"
)

# 日志设置
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# 过滤黑名单，排除百科、词典、社交等非小说站点
BLACKLIST = (
    "baidu.com",
    "zhihu.com",
    "weibo.com",
    "bilibili.com",
    "douyu.com",
)

# 预置的默认小说源，作为兜底
DEFAULT_SOURCES = [
    "www.shuzhaige.com",
    "www.xbiquge.la",
    "www.69shuba.com",
    "www.biquge5200.cc",
]


def _is_novel_site(domain: str) -> bool:
    """判断域名是否可能是小说网站。

    使用一个更全面的黑名单来去除词典、百科、社交媒体、门户、政府/机构类域名。
    返回 True 表示可能是小说站点，False 表示明显不是。
    """
    if not domain:
        return False
    domain = domain.lower()
    BLACKLIST_EXT = (
        "baidu.com",
        "zhihu.com",
        "weibo.com",
        "bilibili.com",
        "douyu.com",
        "zdic.net",
        "dict.",
        "hanyuguoxue",
        "hgcha.com",
        "kanjipedia",
        "jitenon",
        "wikipedia",
        "gov.",
        "edu.",
        "news.",
        "163.com",
        "qq.com",
    )
    return not any(x in domain for x in BLACKLIST_EXT)


def _request_with_retries(
    url: str, timeout: int = 5, retries: int = 2, method: str = "GET", data: Optional[dict] = None
) -> Optional[str]:
    """使用 requests 请求并自动重试，支持 GET/POST，成功返回文本，否则返回 None。

    会设置 `resp.encoding = resp.apparent_encoding` 以修复编码判断问题。
    """
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"}
    attempt = 0
    while attempt < retries:
        try:
            if method.upper() == "POST":
                resp = requests.post(url, headers=headers, timeout=timeout, data=data)
            else:
                resp = requests.get(url, headers=headers, timeout=timeout, params=None)
            resp.raise_for_status()
            # 使用 requests 的推测编码，避免中文乱码
            try:
                resp.encoding = resp.apparent_encoding
            except Exception:
                pass
            return resp.text
        except Exception as e:
            logger.debug("请求失败：%s %s 重试 %s/%s: %s", method, url, attempt + 1, retries, e)
            attempt += 1
            time.sleep(1 + attempt * 0.5)
    return None


def _normalize_url(url: str) -> str:
    """确保 URL 带有 scheme，如果没有则默认添加 http://"""
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.scheme:
        return url
    return f"http://{url}"


def discover_sources(keyword: str, max_results: int = 30) -> List[str]:
    """在 Bing 上搜索并提取搜索结果中的网站域名。

    返回值：域名字符串列表，例如 "www.biquge.com"。
    注意：该函数直接抓取 Bing 搜索结果页面并解析链接，可能受搜索页面结构变化影响。
    """
    # 搜索关键词：使用更宽松的中文关键词以避免过度限制
    query = f"{keyword} 小说 免费阅读"
    # 强制 Bing 返回简体中文 / 中国地区结果
    bing_url = (
        f"https://www.bing.com/search?q={quote_plus(query)}&cc=CN&setlang=zh-hans&mkt=zh-CN"
    )

    # 调试输出：查看 Bing 返回内容以便诊断
    html = _request_with_retries(bing_url)
    if not html:
        print("请求失败，html为空")
        return DEFAULT_SOURCES
    print(f"HTML长度: {len(html)}")
    print(f"HTML前500字符: {html[:500]}")

    # 从搜索结果 HTML 中提取所有 href 链接，然后解析域名
    hrefs = re.findall(r'href\s*=\s*"(https?://[^"]+)"', html)
    domains = []
    seen = set()
    # 只接受常见的中文网站顶级域名，过滤掉明显非目标站点
    allowed_suffixes = (".com", ".net", ".org", ".cc", ".xyz")
    for href in hrefs:
        try:
            parsed = urlparse(href)
            domain = parsed.netloc.lower()
            # 过滤一些常见的非目标域
            if not domain or any(x in domain for x in ("bing.com", "microsoft", "windows")):
                continue
            # 过滤黑名单（包含任意黑名单片段即跳过）
            if any(b in domain for b in BLACKLIST):
                continue
            # 过滤非中文网站（域名必须以指定后缀结尾）
            if not any(domain.endswith(s) for s in allowed_suffixes):
                continue
            # 去除参数或端口
            domain = domain.split(":")[0]
            # 仅添加看起来像小说网站的域名
            if domain not in seen and _is_novel_site(domain):
                seen.add(domain)
                domains.append(domain)
            if len(domains) >= max_results:
                break
        except Exception:
            continue
    # 将默认源加入结果作为兜底，避免结果为空
    for d in DEFAULT_SOURCES:
        if d not in seen:
            domains.append(d)
    return domains


def health_check(url: str, probe_retries: int = 3, timeout: int = 10) -> bool:
    """测试网址是否可访问并能被 trafilatura 提取正文。

    策略：对同一 URL 做多次请求，若任意一次能提取到足够长度的正文（>200 字符），视为可用。
    返回 True/False。
    """
    if not url:
        return False
    url = _normalize_url(url)
    for attempt in range(probe_retries):
        html = _request_with_retries(url, timeout=timeout, retries=1)
        if not html:
            continue
        try:
            text = trafilatura.extract(html, include_comments=False, include_tables=False)
            if text and len(text.strip()) > 200:
                return True
        except Exception as e:
            logger.debug("trafilatura 解析失败：%s -> %s", url, e)
        time.sleep(0.5)
    return False


def _ensure_db(conn: sqlite3.Connection) -> None:
    """确保表存在（如果不存在则创建）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS website_sources (
            id INTEGER PRIMARY KEY,
            base_url TEXT UNIQUE,
            search_pattern TEXT,
            is_active INTEGER DEFAULT 1,
            success_rate INTEGER DEFAULT 100,
            last_checked TEXT
        )
        """
    )
    conn.commit()


def update_sources(db_path: Optional[str] = None, concurrency: int = 6) -> dict:
    """批量检测数据库里所有网址，更新 is_active、success_rate、last_checked 字段。

    db_path: 可选，数据库文件路径；默认使用项目根下的 database/sources.db
    返回值：摘要字典，包含 checked_count、updated_count、errors
    """
    # 推断默认数据库路径 novel_reader/database/sources.db
    if db_path is None:
        root = Path(__file__).resolve().parents[1]
        db_dir = root / "database"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(db_dir / "sources.db")

    conn = sqlite3.connect(db_path)
    try:
        _ensure_db(conn)
        cursor = conn.execute("SELECT id, base_url FROM website_sources")
        rows = cursor.fetchall()
        if not rows:
            return {"checked_count": 0, "updated_count": 0, "errors": []}

        # 并发执行健康检查
        results: List[Tuple[int, str, bool]] = []
        errors: List[str] = []

        def _check_row(row_id: int, base_url: str):
            try:
                ok = health_check(base_url)
                return (row_id, base_url, ok)
            except Exception as e:
                return (row_id, base_url, False)

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_to_id = {executor.submit(_check_row, r[0], r[1]): r for r in rows}
            for fut in concurrent.futures.as_completed(future_to_id):
                row = future_to_id[fut]
                try:
                    row_id, base_url, ok = fut.result()
                    results.append((row_id, base_url, ok))
                except Exception as e:
                    errors.append(f"{row[1]}: {e}")

        updated = 0
        now = datetime.datetime.utcnow().isoformat()
        for row_id, base_url, ok in results:
            success_rate = 100 if ok else 0
            is_active = 1 if ok else 0
            conn.execute(
                "UPDATE website_sources SET is_active = ?, success_rate = ?, last_checked = ? WHERE id = ?",
                (is_active, success_rate, now, row_id),
            )
            updated += 1
        conn.commit()
        return {"checked_count": len(rows), "updated_count": updated, "errors": errors}
    finally:
        conn.close()


__all__ = ["discover_sources", "health_check", "update_sources"]


if __name__ == "__main__":
    # 简单自测（仅在开发环境运行）
    logging.basicConfig(level=logging.DEBUG)
    print(discover_sources("盗墓笔记")[:10])
    print(health_check("https://www.biquge.com"))
