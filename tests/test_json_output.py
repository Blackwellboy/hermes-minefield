"""--json output for every command (plan T3.6)."""

from __future__ import annotations

import json

import pytest

from hermes_minefield.commands.cli import to_json
from hermes_minefield.commands.dispatch import handle_slash


@pytest.mark.parametrize(
    ("cmd", "keys"),
    [
        ("status --json", {"ok", "recorder", "last_verdict"}),
        ("wtf --json", {"ok", "verdict", "classification", "scope", "saved", "artifact"}),
        ("check --json", {"ok", "verdict"}),
        ("doctor --json", {"ok", "verdict"}),
        ("issues --json", {"ok", "items"}),
        ("clear-cache --json", {"ok"}),
    ],
)
def test_json_shapes(cmd, keys, tmp_hermes_home, fresh_recorder):
    data = json.loads(handle_slash(cmd))
    assert keys <= set(data), sorted(data)
    assert "text" not in data


def test_json_is_sanitized():
    out = json.loads(to_json({"ok": True, "text": "x", "note": "token=abc123 at /home/alice/p 10.1.2.3"}))
    assert out["note"] == "[REDACTED] at [REDACTED_PATH] [REDACTED_IP]"


def test_cli_json_flag(tmp_hermes_home, fresh_recorder, capsys):
    import argparse

    from hermes_minefield.commands.cli import minefield_command

    rc = minefield_command(
        argparse.Namespace(minefield_command="wtf", window="1m", session=None, save=None, json=True)
    )
    data = json.loads(capsys.readouterr().out)
    assert data["verdict"] == "UNKNOWN" and rc == 3
