"""The plugin loads in real Hermes and registers what plugin.yaml declares."""

from __future__ import annotations

import yaml

from .conftest import ROOT


def test_plugin_loads_enabled_without_error(hermes_plugins):
    loaded = hermes_plugins.get_plugin_manager()._plugins.get("hermes-minefield")
    assert loaded is not None, "hermes-minefield was not discovered"
    assert loaded.error is None, loaded.error
    assert loaded.enabled is True


def test_declared_hooks_are_registered(hermes_plugins):
    declared = set(yaml.safe_load((ROOT / "plugin.yaml").read_text())["provides_hooks"])
    for hook in declared:
        assert hermes_plugins.has_hook(hook), f"{hook} declared but not registered"
