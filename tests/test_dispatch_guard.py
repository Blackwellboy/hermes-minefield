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


def test_missing_core_is_unknown_with_an_install_hint(tmp_hermes_home, monkeypatch):
    def no_core(**kw):
        raise ModuleNotFoundError("No module named 'minefield'", name="minefield")

    monkeypatch.setattr(dispatch, "run_check", no_core)
    out = slash_result("check")
    assert out["verdict"] == V.UNKNOWN
    assert "model-serving-minefield" in out["text"] and "hermes pm repair" in out["text"]


def test_other_missing_modules_stay_internal_errors(tmp_hermes_home, monkeypatch):
    def other(**kw):
        raise ModuleNotFoundError("No module named 'secret_dep'", name="secret_dep")

    monkeypatch.setattr(dispatch, "run_check", other)
    text = handle_slash("check")
    assert text.startswith("minefield: internal error (ModuleNotFoundError)")
    assert "secret_dep" not in text


def test_budget_refusal_is_shown_not_hidden(tmp_hermes_home, monkeypatch):
    def over(**kw):
        raise RuntimeError("HARD_BUDGET_VIOLATION: plan expects 9 > budget 5")

    monkeypatch.setattr(dispatch, "run_check", over)
    out = slash_result("check")
    assert out["verdict"] == V.UNKNOWN
    assert "plan expects 9 > budget 5" in out["text"]


def test_debug_env_shows_the_traceback_only_when_set(tmp_hermes_home, monkeypatch):
    def boom(**kw):
        raise KeyError("secret-internal-detail")

    monkeypatch.setattr(dispatch, "run_status", boom)
    monkeypatch.delenv("HERMES_PLUGINS_DEBUG", raising=False)
    assert "Traceback" not in handle_slash("status")
    monkeypatch.setenv("HERMES_PLUGINS_DEBUG", "1")
    assert "Traceback" in handle_slash("status")


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
