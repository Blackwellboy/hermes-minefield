"""Hermes PM must be able to install every declared dependency (no direct-URL requirements)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
packaging = pytest.importorskip("packaging.requirements")
yaml = pytest.importorskip("yaml")


def _declared():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    manifest = (
        yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8")).get("python_dependencies") or []
    )
    return project, manifest


def test_no_direct_url_requirements():
    for spec in [*_declared()[0], *_declared()[1]]:
        assert packaging.Requirement(spec).url is None, f"Hermes PM will not install {spec!r}"


def test_pyproject_and_manifest_agree_and_need_core_021():
    project, manifest = _declared()
    assert sorted(project) == sorted(manifest)
    core = [
        packaging.Requirement(s)
        for s in project
        if packaging.Requirement(s).name == "model-serving-minefield"
    ]
    assert core and core[0].specifier.contains("0.2.1") and not core[0].specifier.contains("0.2.0")
