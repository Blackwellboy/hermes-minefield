from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Keep the plugin source importable in editable/local test runs. Minefield itself
# should come from the installed dependency; developers can optionally point at
# a source checkout without baking a machine-specific path into the repository.
paths = [ROOT]
minefield_source = os.environ.get("MINEFIELD_SOURCE")
if minefield_source:
    paths.append(Path(minefield_source).expanduser().resolve())

for path in paths:
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)


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
