"""Diagnostic integrity (plan T1.3 + T1.8): "couldn't test" is UNKNOWN, never PASS."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field

import pytest

from hermes_minefield import verdict as V
from hermes_minefield.cache import CacheEntry, get_entry, put_entry
from hermes_minefield.commands.check import run_check
from hermes_minefield.commands.cli import minefield_command
from hermes_minefield.commands.doctor import run_doctor
from hermes_minefield.commands.wtf import incident_verdict, run_wtf
from hermes_minefield.concurrency import ConcurrencyInfo
from hermes_minefield.fingerprint import fingerprint_for_hermes_target
from hermes_minefield.recorder.events import TOOL_EXECUTED, TOOL_PREPARED, RecorderEvent

DEAD = "http://127.0.0.1:9/v1"  # discard port: connection refused, instantly


@dataclass
class FakePlan:
    expected_requests: int = 3
    selected_ids: tuple = ("a", "b", "c")


@dataclass
class FakeResult:
    requests_executed: int = 3
    request_budget: int | None = 5
    reachable: bool = True
    error: str | None = None
    budget_exceeded: bool = False
    findings: list = field(default_factory=list)


@dataclass
class FakeFinding:
    level: str
    code: str = "x"
    title: str = "t"
    detail: str = ""
    traps: tuple = ()


@dataclass
class FakeSummary:
    findings: tuple = ()
    clean_count: int = 0
    problem_count: int = 0
    inconclusive_count: int = 0
    skipped_probe_count: int = 0


@pytest.fixture()
def configured(tmp_hermes_home):
    (tmp_hermes_home / "config.yaml").write_text(
        f"model:\n  default: test-model\n  base_url: {DEAD}\n", encoding="utf-8"
    )
    return tmp_hermes_home


def fake_minefield(monkeypatch, result: FakeResult, summary: FakeSummary | None = None):
    monkeypatch.setattr("minefield.api.plan_checks", lambda **kw: FakePlan())
    monkeypatch.setattr("minefield.api.run_checks", lambda plan, **kw: result)
    monkeypatch.setattr("minefield.api.summarize", lambda r: summary or FakeSummary())


def cache_key():
    return fingerprint_for_hermes_target(model="test-model", base_url=DEAD).key


def cli(**kw) -> int:
    base = dict(base_url=None, model=None, max_requests=None, force=False, no_detect=False, yes=False)
    base.update(kw)
    return minefield_command(argparse.Namespace(**base))


# --- check (Lite) --------------------------------------------------------


def test_real_dead_endpoint_is_unknown_and_not_cached(configured):
    """F6 repro against real Minefield (no mocks): used to print 0 problems, exit 0, and cache."""
    out = run_check()
    assert out["verdict"] == V.UNKNOWN
    assert out["ok"] is False
    assert "Verdict: UNKNOWN" in out["text"]
    assert get_entry(cache_key()) is None
    assert cli(minefield_command="check") == V.EXIT_UNKNOWN


def test_unreachable_result_is_unknown(configured, monkeypatch):
    fake_minefield(monkeypatch, FakeResult(requests_executed=0, reachable=False, error="target_unreachable"))
    out = run_check()
    assert (out["verdict"], out["ok"], out["error"]) == (V.UNKNOWN, False, "target_unreachable")
    assert get_entry(cache_key()) is None


def test_zero_probes_is_unknown(configured, monkeypatch):
    fake_minefield(monkeypatch, FakeResult(requests_executed=0))
    out = run_check()
    assert out["verdict"] == V.UNKNOWN
    assert out["error"] == "no_probes_executed"
    assert get_entry(cache_key()) is None


def test_budget_violation_is_discarded(configured, monkeypatch):
    fake_minefield(monkeypatch, FakeResult(requests_executed=9, request_budget=5, budget_exceeded=True))
    out = run_check()
    assert out["verdict"] == V.UNKNOWN
    assert "HARD_BUDGET_VIOLATION" in out["text"]
    assert get_entry(cache_key()) is None


def test_all_clean_is_pass_and_cached(configured, monkeypatch):
    fake_minefield(
        monkeypatch, FakeResult(), FakeSummary(findings=(FakeFinding("OK"), FakeFinding("OK")), clean_count=2)
    )
    out = run_check()
    assert out["verdict"] == V.PASS
    assert get_entry(cache_key()).summary["verdict"] == V.PASS
    assert cli(minefield_command="check") == V.EXIT_PASS  # served from cache


def test_problem_is_fail(configured, monkeypatch):
    fake_minefield(
        monkeypatch,
        FakeResult(),
        FakeSummary(findings=(FakeFinding("OK"), FakeFinding("PROBLEM")), clean_count=1, problem_count=1),
    )
    assert cli(minefield_command="check") == V.EXIT_FAIL


def test_inconclusive_only_is_unknown(configured, monkeypatch):
    fake_minefield(
        monkeypatch, FakeResult(), FakeSummary(findings=(FakeFinding("INCONCLUSIVE"),), inconclusive_count=1)
    )
    assert run_check()["verdict"] == V.UNKNOWN


def test_unresolved_target_is_unknown(tmp_hermes_home):
    out = run_check()
    assert out["verdict"] == V.UNKNOWN
    assert "base_url" in out["text"]


def test_legacy_false_green_cache_entry_is_not_pass(configured):
    """Entries cached by the old code for a dead endpoint (0/0/0, no findings) must not read as PASS."""
    put_entry(
        CacheEntry(
            fingerprint=cache_key(),
            checked_at=time.time(),
            mode="lite",
            summary={"clean": 0, "problem": 0, "inconclusive": 0, "findings": []},
            requests_executed=0,
            clean=0,
            problem=0,
            inconclusive=0,
        )
    )
    out = run_check()
    assert out["cached"] is True
    assert out["verdict"] == V.UNKNOWN


# --- doctor ----------------------------------------------------------------


def test_doctor_unreachable_is_unknown(configured, monkeypatch):
    monkeypatch.setattr(
        "hermes_minefield.commands.doctor.probe_concurrency",
        lambda url, **kw: ConcurrencyInfo(4, False, "props.total_slots", "total_slots=4"),
    )
    fake_minefield(monkeypatch, FakeResult(requests_executed=0, reachable=False, error="target_unreachable"))
    out = run_doctor(yes=True)
    assert (out["verdict"], out["ok"]) == (V.UNKNOWN, False)


def test_doctor_blocked_is_exit_2(configured, monkeypatch):
    monkeypatch.setattr(
        "hermes_minefield.commands.doctor.probe_concurrency",
        lambda url, **kw: ConcurrencyInfo(1, True, "props.total_slots", "total_slots=1"),
    )
    assert cli(minefield_command="doctor") == V.EXIT_BLOCKED


# --- wtf -------------------------------------------------------------------


def test_wtf_empty_window_is_unknown(tmp_hermes_home, fresh_recorder):
    out = run_wtf(window="1m")
    assert out["verdict"] == V.UNKNOWN
    assert "no recorder events" in out["text"]


def test_wtf_aligned_is_pass(tmp_hermes_home, fresh_recorder):
    for i in range(3):
        for t in (TOOL_PREPARED, TOOL_EXECUTED):
            fresh_recorder.record(RecorderEvent(type=t, tool_name="read_file", tool_arg_fingerprint=f"f{i}"))
    assert run_wtf(window="1m")["verdict"] == V.PASS


@pytest.mark.parametrize(
    ("classification", "count", "truncated", "expected"),
    [
        ("EXPECTED_BEHAVIOUR", 0, False, V.UNKNOWN),
        ("EXPECTED_BEHAVIOUR", 10, False, V.PASS),
        ("EXPECTED_BEHAVIOUR", 10, True, V.UNKNOWN),  # incomplete evidence can't be PASS
        ("UNKNOWN", 10, False, V.UNKNOWN),
        ("AGENT_TOOL_LOOP", 10, False, V.FAIL),
        ("MODEL_SERVER_BUG", 10, True, V.FAIL),
    ],
)
def test_incident_verdict_table(classification, count, truncated, expected):
    assert incident_verdict(classification, count, truncated=truncated)[0] == expected


def test_exit_codes():
    assert V.exit_code({"verdict": V.PASS, "ok": True}) == 0
    assert V.exit_code({"verdict": V.FAIL, "ok": True}) == 1
    assert V.exit_code({"verdict": V.UNKNOWN, "ok": False}) == 3
    assert V.exit_code({"verdict": V.UNKNOWN, "blocked": True}) == 2
    assert V.exit_code({"ok": True}) == 0
    assert V.exit_code({"ok": False}) == 1


# --- T1.4: cache TTL ---------------------------------------------------------


def _cached_pass(age_days: float):
    put_entry(
        CacheEntry(
            fingerprint=cache_key(),
            checked_at=time.time() - age_days * 86400,
            mode="lite",
            summary={"clean": 2, "problem": 0, "inconclusive": 0, "findings": [], "verdict": V.PASS},
            requests_executed=2,
            clean=2,
            problem=0,
            inconclusive=0,
        )
    )


def test_fresh_cache_is_served(configured):
    _cached_pass(age_days=1)
    out = run_check()
    assert (out["cached"], out["verdict"]) == (True, V.PASS)


def test_expired_cache_is_a_miss(configured, monkeypatch):
    _cached_pass(age_days=31)  # default TTL is 30 days
    fake_minefield(monkeypatch, FakeResult(requests_executed=0, reachable=False, error="target_unreachable"))
    out = run_check()
    assert out["cached"] is False
    assert out["verdict"] == V.UNKNOWN  # re-ran, and the endpoint is down now


def test_status_marks_stale_cache_unknown(configured):
    from hermes_minefield.commands.status import run_status

    _cached_pass(age_days=31)
    out = run_status()
    assert out["last_verdict"] == "UNKNOWN (stale)"
    assert "STALE" in out["text"]
