"""Hermes home resolution (T2.1) and atomic, private storage (T2.6)."""

from __future__ import annotations

import json
import stat
import sys
import time
from pathlib import Path

import pytest

from hermes_minefield import paths
from hermes_minefield.cache import CacheEntry, put_entry
from hermes_minefield.incident.analyze import analyze_events
from hermes_minefield.paths import atomic_write_text, hermes_home


def test_hermes_home_honours_env_via_hermes(tmp_path, monkeypatch):
    pytest.importorskip("hermes_constants")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert hermes_home() == tmp_path.resolve()


def test_hermes_home_uses_hermes_context_override(tmp_path, monkeypatch):
    """Hermes's context-local override must win over the process env (profiles/tasks)."""
    hc = pytest.importorskip("hermes_constants")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "env"))
    monkeypatch.setattr(hc, "get_hermes_home", lambda: tmp_path / "override")
    assert hermes_home() == (tmp_path / "override").resolve()


def test_hermes_home_fallback_without_hermes(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "hermes_constants", None)  # simulate "not installed"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert hermes_home() == tmp_path.resolve()
    monkeypatch.delenv("HERMES_HOME")
    monkeypatch.delenv("HERMES_HOME_DIR", raising=False)
    assert hermes_home() == (Path.home() / ".hermes").resolve()


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")


@posix_only
def test_files_and_dirs_are_private(tmp_hermes_home):
    put_entry(CacheEntry("fp", time.time(), "lite", {}, 0, 0, 0, 0))
    analyze_events([], persist=True)
    root = tmp_hermes_home / "minefield"
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    for f in root.rglob("*"):
        if f.is_file():
            assert stat.S_IMODE(f.stat().st_mode) == 0o600, f
        else:
            assert stat.S_IMODE(f.stat().st_mode) == 0o700, f


def test_atomic_write_leaves_no_partial_file_on_failure(tmp_path, monkeypatch):
    target = tmp_path / "data.json"
    atomic_write_text(target, '{"old": true}')

    real_fsync = paths.os.fsync

    def die(fd):
        raise OSError("disk full")

    monkeypatch.setattr(paths.os, "fsync", die)
    with pytest.raises(OSError):
        atomic_write_text(target, '{"new": true}')
    monkeypatch.setattr(paths.os, "fsync", real_fsync)
    assert json.loads(target.read_text()) == {"old": True}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data.json"]
