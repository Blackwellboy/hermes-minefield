"""wtf defaults to the current session (plan T3.5)."""

from __future__ import annotations

import time

from hermes_minefield.commands.wtf import run_wtf
from hermes_minefield.privacy import stable_hash
from hermes_minefield.recorder.events import TOOL_EXECUTED, TOOL_REQUESTED, RecorderEvent
from hermes_minefield.recorder.store import FlightRecorder


def _loop(rec, sid, t0):
    for i in range(8):
        for t in (TOOL_REQUESTED, TOOL_EXECUTED):
            rec.record(
                RecorderEvent(
                    type=t,
                    ts=t0 + i,
                    session_id_hash=sid,
                    tool_name="read_file",
                    tool_arg_fingerprint="a",
                    result_fingerprint="r",
                )
            )


def _quiet(rec, sid, t0):
    rec.record(RecorderEvent(type=TOOL_REQUESTED, ts=t0, session_id_hash=sid, tool_name="read_file"))
    rec.record(
        RecorderEvent(
            type=TOOL_EXECUTED,
            ts=t0 + 1,
            session_id_hash=sid,
            tool_name="read_file",
            tool_arg_fingerprint="z",
        )
    )


def test_default_is_current_session(tmp_hermes_home, fresh_recorder):
    now = time.time()
    loop_sid, quiet_sid = stable_hash("older", n=16), stable_hash("newest", n=16)
    _loop(fresh_recorder, loop_sid, now - 60)
    _quiet(fresh_recorder, quiet_sid, now - 5)
    current = run_wtf(window="5m")
    assert current["scope"].startswith("current session")
    assert current["classification"] == "EXPECTED_BEHAVIOUR"
    everything = run_wtf(window="5m", session="all")
    assert everything["scope"] == "all sessions"
    assert everything["classification"] == "AGENT_TOOL_LOOP"
    explicit = run_wtf(window="5m", session="older")
    assert explicit["classification"] == "AGENT_TOOL_LOOP"


def test_fresh_process_uses_newest_persisted_session(tmp_path):
    writer = FlightRecorder(persist=True, directory=tmp_path)
    writer.record(RecorderEvent(type=TOOL_EXECUTED, session_id_hash="aaa", tool_name="t"))
    writer.record(RecorderEvent(type=TOOL_EXECUTED, session_id_hash="bbb", tool_name="t"))
    writer.stop()
    fresh = FlightRecorder(persist=True, directory=tmp_path)  # like a new `hermes minefield wtf`
    assert fresh.current_session_hash() == "bbb"
    fresh.stop()


def test_no_sessions_means_all(tmp_hermes_home, fresh_recorder):
    assert run_wtf(window="1m")["scope"] == "all sessions (no session seen yet)"
