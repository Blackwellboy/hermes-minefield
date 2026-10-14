"""Synthetic WTF fixtures: prepare-storm vs real tool loop."""

from __future__ import annotations

import json
import time
from pathlib import Path

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
    """T3.1 lifecycle: prepared = model emitted (post_api_request), requested = Hermes
    dispatched (pre_tool_call), executed = finished (post_tool_call).
    (Rewritten: pre_tool_call used to emit 'prepared', which made prepared == requested.)"""
    from hermes_minefield.recorder import hooks

    calls = [
        {"id": f"c{i}", "type": "function", "function": {"name": "search_files", "arguments": "{}"}}
        for i in range(20)
    ]
    hooks.on_post_api_request(response={"assistant_message": {"tool_calls": calls}}, api_request_id="r1")
    for i in range(20):
        hooks.on_pre_tool_call("search_files", {"q": "x"}, tool_call_id=f"c{i}")
    hooks.on_post_tool_call("search_files", {"q": "x"}, result="ok", tool_call_id="c0", status="ok")
    hooks.on_post_tool_call("search_files", {"q": "y"}, result="ok", tool_call_id="c1", status="ok")
    events = fresh_recorder.freeze(since_seconds=60)
    count = lambda t: sum(1 for e in events if e.type == t)  # noqa: E731
    assert (count("tool.prepared"), count("tool.requested"), count("tool.executed")) == (20, 20, 2)
    prepared_ids = {e.extra["tool_call_id_hash"] for e in events if e.type == "tool.prepared"}
    requested_ids = {e.extra["tool_call_id_hash"] for e in events if e.type == "tool.requested"}
    assert prepared_ids == requested_ids  # same call ids, hashed identically
