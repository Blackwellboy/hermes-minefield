"""Fingerprint → last Lite/Doctor summary cache."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from .paths import cache_dir


@dataclass
class CacheEntry:
    fingerprint: str
    checked_at: float
    mode: str
    summary: dict[str, Any]
    requests_executed: int
    clean: int
    problem: int
    inconclusive: int


def _path() -> Path:
    return cache_dir() / "fingerprint_cache.json"


def load_cache() -> dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {"entries": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"entries": {}}
    except Exception:
        return {"entries": {}}


def save_cache(data: dict[str, Any]) -> None:
    p = _path()
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def get_entry(fingerprint: str) -> Optional[CacheEntry]:
    data = load_cache()
    raw = (data.get("entries") or {}).get(fingerprint)
    if not isinstance(raw, dict):
        return None
    try:
        return CacheEntry(**{k: raw[k] for k in CacheEntry.__dataclass_fields__})
    except Exception:
        return None


def put_entry(entry: CacheEntry) -> None:
    data = load_cache()
    entries = data.setdefault("entries", {})
    entries[entry.fingerprint] = asdict(entry)
    # Bound cache size
    if len(entries) > 200:
        oldest = sorted(entries.items(), key=lambda kv: kv[1].get("checked_at", 0))[:50]
        for k, _ in oldest:
            entries.pop(k, None)
    save_cache(data)


def clear_cache() -> int:
    data = load_cache()
    n = len(data.get("entries") or {})
    save_cache({"entries": {}})
    return n


def is_fresh(entry: CacheEntry, *, ttl_days: int = 30) -> bool:
    age = time.time() - float(entry.checked_at)
    return age <= ttl_days * 86400
