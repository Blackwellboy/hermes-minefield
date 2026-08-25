"""Doctor block returns exit code 2 from plugin handler."""

from __future__ import annotations

import argparse

from hermes_minefield.commands.cli import minefield_command


def test_doctor_blocked_returns_2(tmp_hermes_home, monkeypatch):
    from hermes_minefield.concurrency import ConcurrencyInfo

    monkeypatch.setattr(
        "hermes_minefield.commands.doctor.probe_concurrency",
        lambda url: ConcurrencyInfo(1, True, "props.total_slots", "total_slots=1"),
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
        lambda url: ConcurrencyInfo(1, True, "props.total_slots", "total_slots=1"),
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
