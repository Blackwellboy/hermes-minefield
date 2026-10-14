"""Hermes config loading and target resolution against current Hermes installs.

Hermes environments since 2026-10 ship ruamel.yaml and not PyYAML. The loader
used to `import yaml` only and swallow the ImportError, so every config read as
empty and `/minefield status` said "No model base_url configured" on a config
that sets one.
"""

from __future__ import annotations

import builtins
import sys

import pytest

from hermes_minefield import config as cfgmod
from hermes_minefield.target import resolve_target

CONFIG = """\
model:
  default: demo-model
  provider: demo-lane
providers:
  demo-lane:
    name: Demo lane
    api: http://127.0.0.1:8000/v1
    default_model: demo-model
"""


@pytest.fixture()
def no_pyyaml(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml" or name.startswith("yaml."):
            raise ImportError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "yaml", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_config_reads_with_ruamel_when_pyyaml_is_missing(tmp_hermes_home, no_pyyaml):
    pytest.importorskip("ruamel.yaml")
    (tmp_hermes_home / "config.yaml").write_text(CONFIG, encoding="utf-8")
    data = cfgmod.load_hermes_config()
    assert data["model"]["provider"] == "demo-lane"
    assert cfgmod.last_config_load_error is None


def test_provider_api_key_resolves_the_endpoint(tmp_hermes_home):
    pytest.importorskip("yaml")
    (tmp_hermes_home / "config.yaml").write_text(CONFIG, encoding="utf-8")
    target = resolve_target()
    assert target.base_url == "http://127.0.0.1:8000/v1"
    assert target.model == "demo-model"
    assert "resolved_from_provider:demo-lane" in target.notes


def test_unreadable_config_is_named_in_the_error(tmp_hermes_home, monkeypatch):
    (tmp_hermes_home / "config.yaml").write_text(CONFIG, encoding="utf-8")

    def broken(_text):
        raise ImportError("no YAML library")

    monkeypatch.setattr(cfgmod, "_yaml_safe_load", broken)
    assert cfgmod.load_hermes_config() == {}
    with pytest.raises(ValueError, match="Hermes config was not read: could not read"):
        resolve_target()


def test_explicit_mapping_does_not_borrow_a_stale_load_error(monkeypatch):
    monkeypatch.setattr(cfgmod, "last_config_load_error", "stale")
    with pytest.raises(ValueError) as exc:
        resolve_target(config={})
    assert "stale" not in str(exc.value)
