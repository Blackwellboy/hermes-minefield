"""No exception escapes a command (plan T1.5); slash and CLI share one parser."""

from __future__ import annotations

import argparse

import pytest

from hermes_minefield import verdict as V
from hermes_minefield.commands import dispatch
from hermes_minefield.commands.cli import minefield_command
from hermes_minefield.commands.dispatch import handle_slash, slash_result


def test_slash_check_without_config_explains_base_url(tmp_hermes_home):
    out = slash_result("check")
    assert out["verdict"] == V.UNKNOWN
    assert "base_url" in out["text"]


def test_slash_bad_int_is_a_message_not_a_traceback(tmp_hermes_home):
    out = slash_result("check --max-requests abc")
    assert out["ok"] is False
    assert "invalid int value: 'abc'" in out["text"]


def test_slash_unknown_subcommand(tmp_hermes_home):
    assert "invalid choice: 'bogus'" in handle_slash("bogus")


def test_slash_help_is_returned_as_text(tmp_hermes_home):
    assert handle_slash("doctor --help").startswith("usage: /minefield doctor")


def test_slash_rejects_base_url(tmp_hermes_home):
    out = slash_result("check --base-url http://10.0.0.1:8000/v1")
    assert out["ok"] is False
    assert "CLI-only" in out["text"]


def test_unexpected_exception_is_contained(tmp_hermes_home, monkeypatch):
    def boom(**kw):
        raise KeyError("secret-internal-detail")

    monkeypatch.setattr(dispatch, "run_status", boom)
    text = handle_slash("status")
    assert text.startswith("minefield: internal error (KeyError)")
    assert "secret-internal-detail" not in text
    rc = minefield_command(argparse.Namespace(minefield_command="status", base_url=None, model=None))
    assert rc == 1


def test_value_error_is_reported(tmp_hermes_home, monkeypatch):
    def bad(**kw):
        raise ValueError("max_requests must be >= 0")

    monkeypatch.setattr(dispatch, "run_check", bad)
    assert handle_slash("check") == "minefield: max_requests must be >= 0"


def test_handle_slash_never_raises_even_if_parsing_explodes(monkeypatch):
    monkeypatch.setattr(dispatch, "_slash_parser", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert "internal error" in handle_slash("status")


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "status",
        "wtf",
        "wtf 2m",
        "wtf 1h --session all",
        "incident",
        "issues",
        "clear-cache",
        "contribute",
    ],
)
def test_every_slash_command_returns_text(raw, tmp_hermes_home):
    assert isinstance(handle_slash(raw), str)
