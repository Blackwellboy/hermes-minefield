"""Multi-process-safe persistence (plan T2.5).

Each recorder appends only to its own segment file; readers merge all
segments. Nothing rewrites another process's file, so concurrent Hermes
processes (CLI + gateway) can't lose each other's evidence.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import stat
import sys
import time
from pathlib import Path

import pytest

from hermes_minefield.recorder.events import RecorderEvent
from hermes_minefield.recorder.store import (
    LEGACY_NAME,
    FlightRecorder,
    load_recent_persisted_events,
    persisted_files,
)


def _writer(directory: str, tag: str, n: int, barrier) -> None:
    rec = FlightRecorder(persist=True, directory=Path(directory))
    barrier.wait()
    for i in range(n):
        rec.record(RecorderEvent(type="tool.executed", tool_name=tag, event_id=f"{tag}-{i:05d}"))
        if i % 97 == 0:
            time.sleep(0.001)
    rec.stop()


def test_two_processes_lose_nothing(tmp_path):
    """Gate A scenario: two Hermes processes recording at once."""
    n = 1500
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(2)
    procs = [ctx.Process(target=_writer, args=(str(tmp_path), tag, n, barrier)) for tag in ("cli", "gateway")]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    events = load_recent_persisted_events(directory=tmp_path, max_events=10_000)
    ids = [e.event_id for e in events]
    assert len(ids) == len(set(ids)) == 2 * n
    assert {e.tool_name for e in events} == {"cli", "gateway"}


def test_interleaved_recorders_in_one_dir(tmp_path):
    a = FlightRecorder(persist=True, directory=tmp_path)
    b = FlightRecorder(persist=True, directory=tmp_path)
    for i in range(50):
        a.record(RecorderEvent(type="tool.executed", tool_name="a", event_id=f"a{i}"))
        b.record(RecorderEvent(type="tool.executed", tool_name="b", event_id=f"b{i}"))
        if i % 10 == 0:
            a.flush()
            b.flush()
    a.stop()
    b.stop()
    assert len(persisted_files(tmp_path)) == 2
    fresh = FlightRecorder(persist=True, directory=tmp_path)  # a new `hermes minefield wtf` process
    got = fresh.freeze(since_seconds=600)
    assert len({e.event_id for e in got}) == 100
    fresh.stop()


def test_segment_rolls_over_and_expired_segments_are_deleted(tmp_path):
    rec = FlightRecorder(persist=True, directory=tmp_path, max_bytes=256 * 1024)
    for i in range(3000):
        rec.record(
            RecorderEvent(
                type="tool.executed", tool_name="t", tool_arg_fingerprint="x" * 40, event_id=f"e{i}"
            )
        )
        if i % 200 == 0:
            rec.flush()
    rec.flush()
    segs = persisted_files(tmp_path)
    assert len(segs) >= 2, "segment never rolled over"

    old = segs[-1]
    past = time.time() - rec.retention_seconds - 3600
    os.utime(old, (past, past))
    assert rec.cleanup_segments() >= 1
    assert not old.exists()
    rec.stop()


def test_total_bytes_bounded_oldest_first(tmp_path):
    for i in range(6):
        p = tmp_path / f"events-{i}-0-aaaaaa-1.jsonl"
        p.write_text("x" * 50_000 + "\n")
        t = time.time() - 100 + i
        os.utime(p, (t, t))
    rec = FlightRecorder(persist=True, directory=tmp_path, max_bytes=120_000)
    rec.cleanup_segments()
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == ["events-4-0-aaaaaa-1.jsonl", "events-5-0-aaaaaa-1.jsonl"]
    rec.stop()


def test_legacy_single_file_is_still_read(tmp_path):
    legacy = tmp_path / LEGACY_NAME
    row = {"type": "tool.executed", "ts": time.time(), "event_id": "legacy-1", "tool_name": "t"}
    legacy.write_text(json.dumps(row) + "\n")
    got = load_recent_persisted_events(directory=tmp_path)
    assert [e.event_id for e in got] == ["legacy-1"]


def test_stale_segments_are_skipped_by_mtime(tmp_path):
    p = tmp_path / "events-1-0-aaaaaa-1.jsonl"
    p.write_text(json.dumps({"type": "tool.executed", "ts": time.time() - 30, "event_id": "old"}) + "\n")
    past = time.time() - 3600
    os.utime(p, (past, past))
    assert load_recent_persisted_events(directory=tmp_path, since_seconds=60) == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_segments_are_private(tmp_path):
    rec = FlightRecorder(persist=True, directory=tmp_path)
    rec.record(RecorderEvent(type="tool.executed", tool_name="t"))
    rec.stop()
    (seg,) = persisted_files(tmp_path)
    assert stat.S_IMODE(seg.stat().st_mode) == 0o600


def test_segment_deleted_by_another_process_is_recreated(tmp_path):
    rec = FlightRecorder(persist=True, directory=tmp_path)
    rec.record(RecorderEvent(type="tool.executed", tool_name="t", event_id="one"))
    rec.flush()
    for f in persisted_files(tmp_path):
        f.unlink()
    rec.record(RecorderEvent(type="tool.executed", tool_name="t", event_id="two"))
    rec.stop()
    assert [e.event_id for e in load_recent_persisted_events(directory=tmp_path)] == ["two"]
