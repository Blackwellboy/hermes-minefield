from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MF = Path("/home/lagzilla/worktrees/minefield-phase0-verify")

# Prefer sealed Phase 0 Minefield source
for p in (str(ROOT), str(MF)):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture()
def tmp_hermes_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes_home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


@pytest.fixture()
def fresh_recorder(tmp_hermes_home):
    from hermes_minefield.recorder.store import reset_recorder_for_tests

    return reset_recorder_for_tests()
