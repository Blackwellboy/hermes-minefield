"""Load the plugin through Hermes's real plugin manager (skipped without Hermes)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def hermes_home(tmp_path_factory):
    """A throwaway HERMES_HOME with this repo installed + enabled as a plugin."""
    pytest.importorskip("hermes_cli")
    home = tmp_path_factory.mktemp("hermes_home")
    (home / "plugins").mkdir()
    os.symlink(ROOT, home / "plugins" / "hermes-minefield")
    (home / "config.yaml").write_text(
        "model:\n  default: test-model\n  base_url: http://127.0.0.1:9/v1\n"
        "plugins:\n  enabled: [hermes-minefield]\n",
        encoding="utf-8",
    )
    old = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(home)
    try:
        yield home
    finally:
        if old is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = old


@pytest.fixture(scope="module")
def hermes_plugins(hermes_home):
    """Hermes's plugin module after discovering + loading our plugin."""
    from hermes_cli import plugins as hp

    hp._reset_plugin_managers_for_tests()
    hp.discover_plugins(force=True)
    yield hp
    hp._reset_plugin_managers_for_tests()
