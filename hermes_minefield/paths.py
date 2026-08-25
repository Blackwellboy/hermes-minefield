"""Local storage paths under HERMES_HOME (never world-writable assumptions)."""

from __future__ import annotations

import os
from pathlib import Path


def hermes_home() -> Path:
    raw = os.environ.get("HERMES_HOME") or os.environ.get("HERMES_HOME_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home()).expanduser().resolve()
    except Exception:
        return (Path.home() / ".hermes").resolve()


def minefield_root() -> Path:
    root = hermes_home() / "minefield"
    root.mkdir(parents=True, exist_ok=True)
    return root


def recorder_dir() -> Path:
    d = minefield_root() / "recorder"
    d.mkdir(parents=True, exist_ok=True)
    return d


def incidents_dir() -> Path:
    d = minefield_root() / "incidents"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    d = minefield_root() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def candidates_dir() -> Path:
    d = minefield_root() / "candidates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def drafts_dir() -> Path:
    d = minefield_root() / "drafts"
    d.mkdir(parents=True, exist_ok=True)
    return d
