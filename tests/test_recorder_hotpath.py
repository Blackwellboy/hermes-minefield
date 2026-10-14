"""No disk I/O on the hook hot path (plan T2.4).

Hermes fails *closed* when a pre_tool_call callback is slow or raises: the
user's tool is blocked. So hooks must only touch memory.
"""

from __future__ import annotations

import threading
import time

import pytest

from hermes_minefield.recorder import hooks
from hermes_minefield.recorder import store as store_mod
from hermes_minefield.recorder.events import RecorderEvent
from hermes_minefield.recorder.store import FlightRecorder, load_recent_persisted_events


@pytest.fixture()
def rec(tmp_path):
    r = FlightRecorder(persist=True, path=tmp_path / "events.jsonl")
    yield r
    r.stop()


def test_record_never_writes_on_the_calling_thread(rec, monkeypatch):
    writers: list[str] = []
    real = FlightRecorder._append_rows

    def spy(self, rows):
        writers.append(threading.current_thread().name)
        return real(self, rows)

    monkeypatch.setattr(FlightRecorder, "_append_rows", spy)
    for _ in range(FlightRecorder.FLUSH_BATCH * 3):
        rec.record(RecorderEvent(type="tool.executed", tool_name="t"))
    deadline = time.time() + 5
    while not writers and time.time() < deadline:
        time.sleep(0.02)
    assert writers, "flusher thread never wrote"
    assert set(writers) == {"minefield-recorder-flush"}


def test_slow_disk_does_not_slow_the_hook(tmp_path, monkeypatch):
    """F15: with a 1s-per-write disk, pre_tool_call must still return immediately."""
    monkeypatch.setattr(FlightRecorder, "FLUSH_BATCH", 1)
    real = FlightRecorder._append_rows

    def slow(self, rows):
        time.sleep(1.0)
        return real(self, rows)

    monkeypatch.setattr(FlightRecorder, "_append_rows", slow)
    r = FlightRecorder(persist=True, path=tmp_path / "events.jsonl")
    monkeypatch.setattr(store_mod, "_GLOBAL", r)
    try:
        worst = 0.0
        for i in range(20):
            t0 = time.perf_counter()
            hooks.on_pre_tool_call(tool_name="read_file", args={"path": str(i)}, session_id="s")
            worst = max(worst, time.perf_counter() - t0)
        assert worst < 0.1, f"hook took {worst:.3f}s on a slow disk"
    finally:
        monkeypatch.setattr(FlightRecorder, "_append_rows", real)
        r.stop()


def test_unwritable_disk_never_raises_into_hooks(tmp_path, monkeypatch):
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x")
    r = FlightRecorder(persist=True, path=blocker / "events.jsonl")  # parent is a file
    monkeypatch.setattr(store_mod, "_GLOBAL", r)
    for _ in range(100):
        hooks.on_post_tool_call(tool_name="t", args={}, result="{}", status="ok", session_id="s")
    r.stop()  # final flush fails silently too
    assert len(r.freeze(include_persisted=False)) == 200


def test_flush_is_synchronous(rec, tmp_path):
    rec.record(RecorderEvent(type="tool.executed", tool_name="t", event_id="abc"))
    rec.flush()
    got = load_recent_persisted_events(path=tmp_path / "events.jsonl")
    assert [e.event_id for e in got] == ["abc"]


def test_stop_is_idempotent_and_writes_pending(tmp_path):
    r = FlightRecorder(persist=True, path=tmp_path / "events.jsonl")
    r.record(RecorderEvent(type="tool.executed", tool_name="t", event_id="last"))
    r.stop()
    r.stop()
    assert [e.event_id for e in load_recent_persisted_events(path=tmp_path / "events.jsonl")] == ["last"]
    # After stop, recording still works in memory but nothing restarts the thread.
    r.record(RecorderEvent(type="tool.executed", tool_name="t"))
    assert not (r._thread and r._thread.is_alive())


def test_record_is_cheap():
    r = FlightRecorder(persist=False)
    n = 5000
    t0 = time.perf_counter()
    for i in range(n):
        r.record(RecorderEvent(type="tool.executed", tool_name="t", tool_arg_fingerprint=str(i)))
    per_event_us = (time.perf_counter() - t0) / n * 1e6
    # docs/history/DOGFOOD_20260825.md measured ~10.5 us/event; allow CI noise.
    assert per_event_us < 100, per_event_us
