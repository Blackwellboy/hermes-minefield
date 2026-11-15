"""Doctor block returns exit code 2 from plugin handler."""

from __future__ import annotations

import argparse

from hermes_minefield.commands.cli import minefield_command


def test_doctor_blocked_returns_2(tmp_hermes_home, monkeypatch):
    from hermes_minefield.concurrency import ConcurrencyInfo

    monkeypatch.setattr(
        "hermes_minefield.commands.doctor.probe_concurrency",
        lambda url, **kw: ConcurrencyInfo(1, True, "props.total_slots", "total_slots=1"),
    )
    (tmp_hermes_home / "config.yaml").write_text(
        "model:\n  default: t\n  base_url: http://127.0.0.1:9/v1\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        minefield_command="doctor",
        base_url=None,
        model=None,
        yes=False,
        max_requests=None,
    )
    rc = minefield_command(args)
    assert rc == 2


def test_doctor_success_path_returns_0_when_yes(tmp_hermes_home, monkeypatch):
    """With --yes, guard passes; mock run to avoid network."""

    from hermes_minefield.concurrency import ConcurrencyInfo

    monkeypatch.setattr(
        "hermes_minefield.commands.doctor.probe_concurrency",
        lambda url, **kw: ConcurrencyInfo(1, True, "props.total_slots", "total_slots=1"),
    )

    class _Plan:
        selected_ids = ()
        expected_requests = 0
        max_requests = 0
        mode = "doctor"

    class _Result:
        requests_executed = 0
        request_budget = 0
        findings = []

    class _Summary:
        clean = 0
        problem = 0
        inconclusive = 0
        findings = []

    monkeypatch.setattr(
        "minefield.api.plan_checks",
        lambda **kw: _Plan(),
    )
    monkeypatch.setattr(
        "minefield.api.run_checks",
        lambda plan, **kw: _Result(),
    )
    monkeypatch.setattr(
        "minefield.api.summarize",
        lambda result: _Summary(),
    )
    (tmp_hermes_home / "config.yaml").write_text(
        "model:\n  default: t\n  base_url: http://127.0.0.1:9/v1\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        minefield_command="doctor",
        base_url=None,
        model=None,
        yes=True,
        max_requests=None,
    )
    # run_doctor imports minefield.api inside function — patch via module path used after import
    import hermes_minefield.commands.doctor as doc

    def fake_run_doctor(**kwargs):
        return {"ok": True, "blocked": False, "text": "ok", "requests_executed": 0}

    monkeypatch.setattr(doc, "run_doctor", fake_run_doctor)
    # dispatch imports run_doctor at call time from .doctor
    import hermes_minefield.commands.dispatch as disp

    monkeypatch.setattr(disp, "run_doctor", fake_run_doctor)
    rc = minefield_command(args)
    assert rc == 0


def _multi_slot(monkeypatch, slots: int = 4):
    from hermes_minefield.concurrency import ConcurrencyInfo

    monkeypatch.setattr(
        "hermes_minefield.commands.doctor.probe_concurrency",
        lambda url, **kw: ConcurrencyInfo(slots, False, "props.total_slots", f"total_slots={slots}"),
    )


def _forbid_core_run(monkeypatch):
    import minefield.api as api

    def boom(*a, **kw):
        raise AssertionError("the Doctor must not plan or run without --yes")

    monkeypatch.setattr(api, "plan_checks", boom)
    monkeypatch.setattr(api, "run_checks", boom)


def test_chat_doctor_never_runs_without_yes_even_on_a_multi_slot_server(tmp_hermes_home, monkeypatch):
    """The menu says the Doctor sends nothing until --yes. The concurrency guard alone let a bare
    `/minefield doctor` (or `/minefield 5`) run it on a server with several slots."""
    import pytest

    pytest.importorskip("minefield.api")
    from hermes_minefield.commands.dispatch import slash_result

    (tmp_hermes_home / "config.yaml").write_text(
        "model:\n  default: t\n  base_url: http://127.0.0.1:9/v1\n", encoding="utf-8"
    )
    _multi_slot(monkeypatch)
    _forbid_core_run(monkeypatch)
    for raw in ("doctor", "5"):
        out = slash_result(raw)
        assert out["blocked"] is True, raw
        assert out["verdict"] == "UNKNOWN", raw
        assert out["requests_executed"] == 0, raw
        assert "/minefield doctor --yes" in out["text"], raw
        assert "total_slots=4" in out["text"], raw


def test_cli_doctor_on_a_multi_slot_server_still_runs_without_yes(tmp_hermes_home, monkeypatch):
    """The terminal keeps its documented rule: --yes only for single-slot or unknown concurrency."""
    import pytest

    api = pytest.importorskip("minefield.api")
    from hermes_minefield.commands import dispatch

    (tmp_hermes_home / "config.yaml").write_text(
        "model:\n  default: t\n  base_url: http://127.0.0.1:9/v1\n", encoding="utf-8"
    )
    _multi_slot(monkeypatch)
    planned = []

    def stop_at_planning(**kw):
        planned.append(kw)
        raise ValueError("stop here")

    monkeypatch.setattr(api, "plan_checks", stop_at_planning)
    out = dispatch.handle_cli(argparse.Namespace(minefield_command="doctor", yes=False))
    assert planned, "the CLI path should have reached planning"
    assert out.get("blocked") is not True
