"""Target resolution through Hermes, with credentials that never leak (plan T2.3)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from hermes_minefield.commands.check import run_check
from hermes_minefield.commands.doctor import run_doctor
from hermes_minefield.commands.status import run_status
from hermes_minefield.concurrency import ConcurrencyInfo
from hermes_minefield.target import resolve_target

KEY = "sk-SENTINELKEY-0123456789abcdefghij"
RT_URL = "http://llm.internal:8080/v1"


@pytest.fixture()
def runtime(monkeypatch):
    calls = {}

    def fake(**kw):
        calls.update(kw)
        return {
            "provider": "custom",
            "base_url": RT_URL + "/",
            "api_key": KEY,
            "api_mode": "chat_completions",
        }

    monkeypatch.setattr("hermes_cli.runtime_provider.resolve_runtime_provider", fake)
    return calls


pytest.importorskip("hermes_cli.runtime_provider")


def test_uses_hermes_runtime(tmp_hermes_home, runtime):
    t = resolve_target(model="m")
    assert (t.base_url, t.api_key, t.source, t.provider) == (RT_URL, KEY, "hermes_runtime", "custom")
    assert runtime["target_model"] == "m"
    assert KEY not in repr(t)


def test_runtime_failure_falls_back_to_config(tmp_hermes_home, monkeypatch):
    def boom(**kw):
        raise RuntimeError("no creds")

    monkeypatch.setattr("hermes_cli.runtime_provider.resolve_runtime_provider", boom)
    (tmp_hermes_home / "config.yaml").write_text("model:\n  default: m\n  base_url: http://cfg:1/v1\n")
    t = resolve_target()
    assert (t.base_url, t.api_key, t.source) == ("http://cfg:1/v1", None, "hermes_config")


def test_runtime_without_url_falls_back(tmp_hermes_home, monkeypatch):
    monkeypatch.setattr("hermes_cli.runtime_provider.resolve_runtime_provider", lambda **kw: {"api_key": KEY})
    with pytest.raises(ValueError, match="base_url"):
        resolve_target()


def test_callable_key_is_never_invoked(tmp_hermes_home, monkeypatch):
    def key_provider():
        raise AssertionError("must not be called")

    monkeypatch.setattr(
        "hermes_cli.runtime_provider.resolve_runtime_provider",
        lambda **kw: {"base_url": RT_URL, "api_key": key_provider},
    )
    assert resolve_target().api_key is None


def test_explicit_other_host_gets_no_key(tmp_hermes_home, runtime):
    t = resolve_target(base_url="http://somewhere-else:9/v1")
    assert t.api_key is None


def test_explicit_same_host_gets_key(tmp_hermes_home, runtime):
    assert resolve_target(base_url=RT_URL).api_key == KEY


@dataclass
class _Plan:
    expected_requests: int = 1
    selected_ids: tuple = ("a",)


@dataclass
class _Result:
    requests_executed: int = 1
    request_budget: int = 5
    reachable: bool = True
    error: str | None = None
    budget_exceeded: bool = False


@dataclass
class _Summary:
    findings: tuple = field(default_factory=lambda: ({"level": "OK", "title": "t", "detail": f"key {KEY}"},))
    clean_count: int = 1
    problem_count: int = 0
    inconclusive_count: int = 0
    skipped_probe_count: int = 0


def test_key_reaches_minefield_but_never_output_or_disk(tmp_hermes_home, runtime, monkeypatch):
    seen = {}
    monkeypatch.setattr("minefield.api.plan_checks", lambda **kw: seen.setdefault("plan", kw) and _Plan())
    monkeypatch.setattr(
        "minefield.api.run_checks", lambda plan, **kw: seen.setdefault("run", kw) and _Result()
    )
    monkeypatch.setattr("minefield.api.summarize", lambda r: _Summary())
    monkeypatch.setattr(
        "hermes_minefield.commands.doctor.probe_concurrency",
        lambda url, **kw: (
            seen.setdefault("probe", kw) and ConcurrencyInfo(4, False, "props", "total_slots=4")
        ),
    )
    outs = [run_check(force=True), run_doctor(yes=True), run_status()]
    assert (
        seen["plan"]["api_key"] == KEY and seen["run"]["api_key"] == KEY and seen["probe"]["api_key"] == KEY
    )
    blob = json.dumps(outs, default=str)
    assert "SENTINELKEY" not in blob
    for f in tmp_hermes_home.rglob("*"):
        if f.is_file():
            assert "SENTINELKEY" not in f.read_text(errors="replace"), f


def test_non_openai_provider_is_unknown_not_probed(tmp_hermes_home, monkeypatch):
    """E.g. Bedrock via AWS env: not a chat-completions API, so Minefield can't test it."""
    monkeypatch.setattr(
        "hermes_cli.runtime_provider.resolve_runtime_provider",
        lambda **kw: {
            "provider": "bedrock",
            "api_mode": "bedrock_converse",
            "base_url": "https://bedrock.example",
        },
    )
    monkeypatch.setattr("minefield.api.plan_checks", lambda **kw: pytest.fail("must not probe"))
    out = run_check()
    assert out["verdict"] == "UNKNOWN"
    assert "bedrock_converse" in out["text"]
