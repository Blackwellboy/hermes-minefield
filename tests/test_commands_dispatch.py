"""Slash/CLI dispatch smoke without live model calls."""

from __future__ import annotations

import json
import time

from hermes_minefield.commands.dispatch import handle_slash
from hermes_minefield.incident.analyze import analyze_events
from hermes_minefield.recorder.events import RecorderEvent, TOOL_EXECUTED, TOOL_PREPARED
from hermes_minefield.recorder.store import get_recorder


def test_slash_help():
    text = handle_slash("")
    assert "/minefield check" in text
    assert "/minefield wtf" in text


def test_slash_status(tmp_hermes_home, monkeypatch):
    # Provide minimal hermes config so status doesn't crash
    cfg = {
        "model": {
            "default": "test-model",
            "base_url": "http://127.0.0.1:9/v1",
            "provider": "local",
        }
    }
    (tmp_hermes_home / "config.yaml").write_text(
        __import__("yaml").dump(cfg) if False else "model:\n  default: test\n  base_url: http://127.0.0.1:9/v1\n",
        encoding="utf-8",
    )
    text = handle_slash("status")
    assert "Minefield status" in text
    assert "recorder" in text.lower()


def test_slash_wtf_with_injected_events(tmp_hermes_home, fresh_recorder):
    now = time.time()
    for i in range(30):
        fresh_recorder.record(
            RecorderEvent(
                type=TOOL_PREPARED,
                ts=now - 30 + i,
                tool_name="search_files",
                tool_arg_fingerprint="x",
            )
        )
    fresh_recorder.record(
        RecorderEvent(
            type=TOOL_EXECUTED,
            ts=now,
            tool_name="search_files",
            tool_arg_fingerprint="x",
            success=True,
        )
    )
    # Ensure get_recorder returns the fresh one
    text = handle_slash("wtf 2m")
    assert "MINEFIELD INCIDENT" in text
    assert "HERMES_UI_ORCHESTRATION" in text or "Actual executions" in text


def test_incident_alias(tmp_hermes_home, fresh_recorder):
    text = handle_slash("incident 1m")
    assert "MINEFIELD INCIDENT" in text or "Minefield" in text


def test_contribute_and_issues(tmp_hermes_home):
    events = [
        RecorderEvent(type=TOOL_PREPARED, tool_name="search_files", tool_arg_fingerprint="a")
        for _ in range(15)
    ]
    events.append(
        RecorderEvent(type=TOOL_EXECUTED, tool_name="search_files", tool_arg_fingerprint="a", success=True)
    )
    art = analyze_events(events, persist=True)
    text = handle_slash(f"contribute --incident {art.incident_id}")
    assert "candidate" in text.lower()
    assert "OFFICIAL" in text or "trap #" in text.lower() or "none" in text.lower()
    issues = handle_slash("issues")
    assert art.incident_id in issues or "MINEFIELD ISSUES" in issues


def test_doctor_guard_without_yes(tmp_hermes_home, monkeypatch):
    from hermes_minefield.commands.doctor import run_doctor

    # Force unknown concurrency path
    monkeypatch.setattr(
        "hermes_minefield.commands.doctor.probe_concurrency",
        lambda url: __import__("hermes_minefield.concurrency", fromlist=["ConcurrencyInfo"]).ConcurrencyInfo(
            None, False, "unknown", "UNKNOWN"
        ),
    )
    (tmp_hermes_home / "config.yaml").write_text(
        "model:\n  default: t\n  base_url: http://127.0.0.1:9/v1\n",
        encoding="utf-8",
    )
    out = run_doctor(yes=False)
    assert out["blocked"] is True
    assert "UNKNOWN" in out["text"] or "monopolize" in out["text"].lower() or "confirm" in out["text"].lower()
