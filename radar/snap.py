"""Snapshots: yesterday's state of each signal, gzip JSON files in the state directory."""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from .diagnostics import log


def load(path: Path):
    log.debug("[快照] %s %s", "读取" if path.exists() else "尚无历史", path)
    return json.loads(gzip.decompress(path.read_bytes())) if path.exists() else None


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode()))
    log.debug("[快照] 写入 %s，条目=%d，压缩后=%d bytes", path, len(data), path.stat().st_size)
