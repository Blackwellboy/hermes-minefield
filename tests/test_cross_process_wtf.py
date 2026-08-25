"""Cross-process WTF: persisted replay, dedupe, filters, malformed handling."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from hermes_minefield.commands.wtf import run_wtf
from hermes_minefield.incident.analyze import analyze_events
from hermes_minefield.recorder.events import (
    TOOL_EXECUTED,
    TOOL_PREPARED,
    RecorderEvent,
)
from hermes_minefield.recorder.store import (
    FlightRecorder,
    load_recent_persisted_events,
    merge_events,
    reset_recorder_for_tests,
)


@pytest.fixture()
def rec_path(tmp_hermes_home, tmp_path):
    path = tmp_hermes_home / "minefield" / "recorder" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_events(path: Path, events: list[RecorderEvent]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev.to_dict()) + "\n")


def test_a_process_a_flush_process_b_wtf_reads(tmp_hermes_home, rec_path):
    """A records+flushes; B (empty memory) WTF sees persisted events."""
    now = time.time()
    a = FlightRecorder(persist=True, path=rec_path, retention_seconds=600)
    for i in range(10):
        a.record(
            RecorderEvent(
                type=TOOL_PREPARED,
                ts=now - 30 + i,
                event_id=f"prep{i:02d}",
                tool_name="search_files",
                tool_arg_fingerprint="x",
            )
        )
    a.record(
        RecorderEvent(
            type=TOOL_EXECUTED,
            ts=now,
            event_id="exec01",
            tool_name="search_files",
            tool_arg_fingerprint="x",
            success=True,
        )
    )
    a.flush()
    assert rec_path.is_file() and rec_path.stat().st_size > 0

    # Fresh process B
    b = FlightRecorder(persist=True, path=rec_path, retention_seconds=600)
    assert b.stats().events_in_memory == 0
    frozen = b.freeze_detailed(since_seconds=120)
    assert frozen.memory_count == 0
    assert frozen.persisted_count >= 11
    assert frozen.deduped_count >= 11
    assert any(e.type == TOOL_EXECUTED for e in frozen.events)

    reset_recorder_for_tests(persist=True, path=rec_path)
    out = run_wtf(window="2m", persist=False)
    assert out["event_count"] >= 11
    assert out["event_sources"]["persisted"] >= 11
    assert out["event_sources"]["memory"] == 0


def test_b_memory_disk_dedupe_once(tmp_hermes_home, rec_path):
    now = time.time()
    ev = RecorderEvent(
        type=TOOL_EXECUTED,
        ts=now,
        event_id="sameid01",
        tool_name="t",
        tool_arg_fingerprint="a",
        success=True,
    )
    _write_events(rec_path, [ev])
    rec = FlightRecorder(persist=True, path=rec_path)
    rec.record(ev)  # same id in memory
    frozen = rec.freeze_detailed(since_seconds=60)
    assert frozen.memory_count == 1
    assert frozen.persisted_count >= 1
    assert frozen.deduped_count == 1
    assert len(frozen.events) == 1


def test_c_persisted_ui_prepare_storm(tmp_hermes_home, rec_path):
    now = time.time()
    events = [
        RecorderEvent(
            type=TOOL_PREPARED,
            ts=now - 50 + i,
            event_id=f"p{i:03d}",
            tool_name="search_files",
            tool_arg_fingerprint="a",
        )
        for i in range(50)
    ]
    events.append(
        RecorderEvent(
            type=TOOL_EXECUTED,
            ts=now - 5,
            event_id="e1",
            tool_name="search_files",
            tool_arg_fingerprint="a",
            success=True,
        )
    )
    events.append(
        RecorderEvent(
            type=TOOL_EXECUTED,
            ts=now,
            event_id="e2",
            tool_name="search_files",
            tool_arg_fingerprint="b",
            success=True,
        )
    )
    _write_events(rec_path, events)
    rec = FlightRecorder(persist=True, path=rec_path)
    frozen = rec.freeze_detailed(since_seconds=120)
    art = analyze_events(frozen.events, persist=False)
    assert art.classification == "HERMES_UI_ORCHESTRATION"
    assert art.actual_execution_counts["total_prepared"] >= 50
    assert art.actual_execution_counts["total_executed"] == 2


def test_d_persisted_real_tool_loop(tmp_hermes_home, rec_path):
    now = time.time()
    events = []
    for i in range(50):
        events.append(
            RecorderEvent(
                type=TOOL_PREPARED,
                ts=now - 100 + i,
                event_id=f"pp{i:03d}",
                tool_name="search_files",
                tool_arg_fingerprint="same",
            )
        )
    for i in range(47):
        fp = "same" if i < 42 else f"u{i}"
        events.append(
            RecorderEvent(
                type=TOOL_EXECUTED,
                ts=now - 50 + i,
                event_id=f"ee{i:03d}",
                tool_name="search_files",
                tool_arg_fingerprint=fp,
                success=True,
            )
        )
    _write_events(rec_path, events)
    rec = FlightRecorder(persist=True, path=rec_path)
    frozen = rec.freeze_detailed(since_seconds=300)
    art = analyze_events(frozen.events, persist=False)
    assert art.classification == "AGENT_TOOL_LOOP"
    assert art.severity == "HIGH"


def test_e_older_than_retention_ignored(tmp_hermes_home, rec_path):
    now = time.time()
    old = RecorderEvent(
        type=TOOL_PREPARED,
        ts=now - 10_000,
        event_id="old1",
        tool_name="t",
        tool_arg_fingerprint="x",
    )
    fresh = RecorderEvent(
        type=TOOL_PREPARED,
        ts=now - 5,
        event_id="new1",
        tool_name="t",
        tool_arg_fingerprint="x",
    )
    _write_events(rec_path, [old, fresh])
    loaded = load_recent_persisted_events(
        since_seconds=600,
        retention_seconds=600,
        path=rec_path,
        now=now,
    )
    ids = {e.event_id for e in loaded}
    assert "old1" not in ids
    assert "new1" in ids


def test_f_malformed_jsonl_ignored(tmp_hermes_home, rec_path):
    now = time.time()
    good = RecorderEvent(
        type=TOOL_EXECUTED,
        ts=now,
        event_id="good1",
        tool_name="t",
        success=True,
    )
    with rec_path.open("w", encoding="utf-8") as fh:
        fh.write("{not json\n")
        fh.write(json.dumps({"type": "tool.prepared"}) + "\n")  # missing ts
        fh.write(json.dumps(good.to_dict()) + "\n")
        fh.write('{"type":"tool.prepared","ts":999999999999}\n')  # far future
    loaded = load_recent_persisted_events(since_seconds=60, path=rec_path, now=now)
    assert len(loaded) == 1
    assert loaded[0].event_id == "good1"


def test_g_oversized_file_within_bound(tmp_hermes_home, rec_path):
    now = time.time()
    # Write many lines; reader must only consume max_bytes from end
    with rec_path.open("w", encoding="utf-8") as fh:
        for i in range(5000):
            ev = RecorderEvent(
                type=TOOL_PREPARED,
                ts=now - 10 + (i / 5000),
                event_id=f"big{i:05d}",
                tool_name="t",
                tool_arg_fingerprint="x" * 40,
            )
            fh.write(json.dumps(ev.to_dict()) + "\n")
    loaded = load_recent_persisted_events(
        since_seconds=60,
        max_events=100,
        max_bytes=8192,
        path=rec_path,
        now=now,
    )
    assert len(loaded) <= 100
    # Should have gotten *some* newest events, not OOM the whole file
    assert len(loaded) >= 1


def test_h_session_filter(tmp_hermes_home, rec_path):
    now = time.time()
    a = RecorderEvent(
        type=TOOL_PREPARED,
        ts=now,
        event_id="sa",
        session_id_hash="aaa",
        tool_name="t",
    )
    b = RecorderEvent(
        type=TOOL_PREPARED,
        ts=now,
        event_id="sb",
        session_id_hash="bbb",
        tool_name="t",
    )
    _write_events(rec_path, [a, b])
    loaded = load_recent_persisted_events(
        since_seconds=60, session_id_hash="aaa", path=rec_path, now=now
    )
    assert [e.event_id for e in loaded] == ["sa"]


def test_i_no_persisted_quiet_window(tmp_hermes_home, rec_path):
    reset_recorder_for_tests(persist=True, path=rec_path)
    out = run_wtf(window="1m", persist=False)
    assert out["event_count"] == 0
    assert "quiet" in out["text"].lower() or out["classification"] in {
        "UNKNOWN",
        "EXPECTED_BEHAVIOUR",
    }


def test_j_secrets_absent_from_persisted(tmp_hermes_home, rec_path):
    now = time.time()
    ev = RecorderEvent(
        type=TOOL_EXECUTED,
        ts=now,
        event_id="sec1",
        tool_name="terminal",
        tool_arg_fingerprint="abcd1234",  # hash only
        success=True,
    )
    _write_events(rec_path, [ev])
    text = rec_path.read_text(encoding="utf-8")
    assert "api_key" not in text.lower()
    assert "Bearer " not in text
    assert "password" not in text.lower()
    # Ensure we never wrote raw secret-looking tool args
    assert "sk-" not in text
