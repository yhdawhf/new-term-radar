"""Opt-in execution trace. Reports stay on stdout; diagnostics go to stderr/a file."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("radar")
log.addHandler(logging.NullHandler())
log.propagate = False


def configure(verbose: bool, path: str | None = None) -> None:
    # main() is also called repeatedly by tests/embedders: never duplicate handlers.
    for handler in log.handlers[:]:
        handler.close()
        log.removeHandler(handler)
    log.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S%z")
    if verbose:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)
        log.addHandler(handler)
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(target, encoding="utf-8")
        handler.setFormatter(formatter)
        log.addHandler(handler)
    if not log.handlers:
        log.addHandler(logging.NullHandler())


def result(label: str, block: dict) -> None:
    """Summarise counts/status only; never dump config, credentials or API bodies."""
    status = "失败" if block.get("error") else "跳过" if block.get("skipped") or block.get("off") else "完成"
    fields = {k: v for k, v in block.items() if isinstance(v, (int, float, bool))}
    for k in ("terms", "repos", "queries", "checked", "rows"):
        if isinstance(block.get(k), list):
            fields[k] = len(block[k])
    log.info("[%s] %s %s", label, status, fields)
    if block.get("error"):
        log.warning("[%s] %s", label, block["error"])
    if block.get("first_run"):
        log.info("[%s] 首次快照；依赖历史差分的信号从后续运行开始产出。GitHub 可用平均星速筛选。", label)
    for site, row in block.get("sites", {}).items() if isinstance(block.get("sites"), dict) else ():
        result(f"{label}/{site}", row)
