"""One version everywhere (plan T6.1)."""

from __future__ import annotations

from pathlib import Path

import yaml

from hermes_minefield.version import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_version_matches_package():
    assert yaml.safe_load((ROOT / "plugin.yaml").read_text())["version"] == __version__


def test_pyproject_reads_version_from_package():
    text = (ROOT / "pyproject.toml").read_text()
    assert 'dynamic = ["version"]' in text
    assert 'attr = "hermes_minefield.version.__version__"' in text


def test_changelog_has_current_version():
    assert f"## [{__version__}]" in (ROOT / "CHANGELOG.md").read_text()
