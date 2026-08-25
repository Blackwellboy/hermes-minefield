"""Synthetic WTF fixtures: prepare-storm vs real tool loop."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from hermes_minefield.incident.analyze import analyze_events
from hermes_minefield.recorder.events import RecorderEvent

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def _load_events(name: str):
    doc = json.loads((FIX / name).read_text(encoding="utf-8"))
    now = time.time()
    events = []
    for row in doc["events"]:
        events.append(
            RecorderEvent(
                type=row["type"],
                ts=now - (doc["events"][-1]["offset_s"] - row["offset_s"]),
                tool_name=row.get("tool_name"),
                tool_arg_fingerprint=row.get("tool_arg_fingerprint"),
                success=row.get("success"),
            )
        )
    return doc, events


def test_fixture_a_ui_prepare_storm(tmp_hermes_home):
    doc, events = _load_events("wtf_ui_prepare_storm.json")
    art = analyze_events(events, persist=True)
    assert art.classification == doc["expected_classification"]
    assert art.actual_execution_counts["total_prepared"] >= doc["expected_min_prepared"]
    assert art.actual_execution_counts["total_executed"] == doc["expected_executed"]
    assert art.is_engineering_bug is True
    assert art.serving_failure is False
    assert art.is_minefield_trap is False
    assert not art.known_trap_matches


def test_fixture_b_real_tool_loop(tmp_hermes_home):
    doc, events = _load_events("wtf_real_tool_loop.json")
    art = analyze_events(events, persist=True)
    assert art.classification == doc["expected_classification"]
    assert art.actual_execution_counts["total_prepared"] >= doc["expected_min_prepared"]
    assert art.actual_execution_counts["total_executed"] >= doc["expected_min_executed"]
    assert art.repeated_call_counts["dominant_equivalent"] >= doc["expected_min_equivalent"] - 5
    assert art.severity == "HIGH"
    assert art.is_engineering_bug is True
    assert art.is_minefield_trap is False


def test_prepare_vs_execute_distinction(fresh_recorder):
    from hermes_minefield.recorder import hooks

    for _ in range(20):
        hooks.on_pre_tool_call("search_files", {"q": "x"})
    hooks.on_post_tool_call("search_files", {"q": "x"}, result="ok")
    hooks.on_post_tool_call("search_files", {"q": "y"}, result="ok")
    events = fresh_recorder.freeze(since_seconds=60)
    prepared = [e for e in events if e.type == "tool.prepared"]
    executed = [e for e in events if e.type == "tool.executed"]
    assert len(prepared) == 20
    assert len(executed) == 2
