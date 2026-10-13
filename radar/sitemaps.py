"""Signal ③: pages other sites added since the last run.

Reads the public sitemaps listed in config.json ("sitemaps"), keeps the last run's URLs
in a snapshot, and turns the new URLs into terms: a word that three or more new URLs
share, and that the site's older URLs rarely carried, is a surge.

    "sitemaps": {
      "glama":   {"index": "https://glama.ai/sitemap.xml", "shards": "/mcp-servers/\\\\d+\\\\.xml$", "pause": 2},
      "lobehub": {"index": "https://lobehub.com/sitemap/mcp.xml", "pause": 5, "strip_locale": true}
    }

`index` is a sitemap index when `shards` (a regex) picks the sub-sitemaps to read, or a
plain sitemap when `shards` is left out. `pause` is the seconds between requests to that
site: keep each site's robots.txt and crawl-delay. `strip_locale` drops a leading
/en/ or /zh-CN/ so one new entry in 17 languages counts once.

A site that fails is skipped for the day and keeps its snapshot, since the URLs it
lacks would come back tomorrow as "new".
"""
from __future__ import annotations

import gzip
import re
import time
import urllib.request
from pathlib import Path

from . import UA, snap
from .diagnostics import log
from .terms import by_source, surges

TIMEOUT = 40
RETRIES = 3
RETRY_PAUSE = 10
MIN_URLS = 3
TOP = 25
DEFAULT_PAUSE = 3
_LOCALE = r"^(https?://[^/]+)/[a-z]{2}(?:-[A-Za-z]{2,4})?(?=/)"
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def fetch(url: str) -> str:
    req = urllib.request.Request(url.replace("&amp;", "&"), headers={"User-Agent": UA})
    for attempt in range(RETRIES):
        log.debug("[Sitemap 请求] GET %s 尝试=%d/%d", url, attempt + 1, RETRIES)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                body = res.read()
            return (gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body).decode("utf-8", "replace")
        except (OSError, ValueError) as exc:
            log.warning("[Sitemap 请求失败] %s %s", url, type(exc).__name__)
            if attempt == RETRIES - 1:
                raise
            time.sleep(RETRY_PAUSE * (attempt + 1))
    return ""


def site_urls(index: str, shards: str | None, pause: float, strip_locale: bool = False) -> set[str]:
    files = [index] if not shards else \
        [u for u in _LOC.findall(fetch(index)) if re.search(shards, u.replace("&amp;", "&"))]
    urls: set[str] = set()
    log.info("[Sitemap] %s 匹配文件=%d，请求间隔=%ss，合并语言路径=%s", index, len(files), pause, strip_locale)
    for i, u in enumerate(files):
        if i or shards:
            time.sleep(pause)
        urls.update(x.replace("&amp;", "&") for x in _LOC.findall(fetch(u)))
    return {re.sub(_LOCALE, r"\1", u) for u in urls} if strip_locale else urls


def slug_text(url: str) -> str:
    """The words a URL carries: its path after the domain, without ids or file suffixes."""
    path = re.sub(r"^https?://[^/]+", "", url).split("?")[0]
    path = re.sub(r"\b[0-9a-f]{8,}\b|\.(html|xml)$", " ", path)
    return re.sub(r"[/_\-]+", " ", path)


def diff(cfg: dict, state: Path) -> dict:
    """New URLs per site against the stored snapshot, then the terms that surge in them."""
    if not cfg["sitemaps"]:
        log.info("[Sitemap] 未配置站点")
        return {"skipped": True}
    report, recent, baseline = {}, [], []
    for i, (site, s) in enumerate(cfg["sitemaps"].items()):
        path = state / "sitemaps" / f"{re.sub(r'[^A-Za-z0-9._-]', '_', site)}.json.gz"
        stored = snap.load(path)
        old = set(stored) if stored is not None else None
        pause = s.get("pause", DEFAULT_PAUSE)
        try:
            if i:
                time.sleep(pause)   # several entries can point at one host
            now = site_urls(s["index"], s.get("shards"), pause, bool(s.get("strip_locale")))
        except Exception as exc:  # noqa: BLE001 — one site down must not stop the others
            report[site] = {"error": str(exc)[:120]}
            log.warning("[Sitemap/%s] 失败，保留旧快照：%s", site, report[site]["error"])
            continue
        new = sorted(now - old) if old is not None else []
        report[site] = {"urls": len(now), "new": len(new), "first_run": old is None, "sample": new[:8]}
        log.info("[Sitemap/%s] 旧网址=%s，当前=%d，新增=%d", site, len(old) if old is not None else "无快照", len(now), len(new))
        recent += [(u, slug_text(u)) for u in new]
        baseline += [(u, slug_text(u)) for u in (old or set())]
        if now:   # an empty answer (blocked, broken) keeps the old snapshot
            snap.save(path, sorted(now))
    ratio = len(recent) / max(len(baseline), 1)
    log.info("[Sitemap 词频] 新网址=%d，基线网址=%d，比例=%.6f；至少%d个不同新网址共现，lift=新频次/(旧频次×比例+1)",
             len(recent), len(baseline), ratio, MIN_URLS)
    return {"sites": report, "terms": surges(by_source(recent), by_source(baseline), ratio, MIN_URLS, TOP)}
