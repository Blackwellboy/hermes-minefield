"""Flight recorder bounds + privacy."""

from __future__ import annotations

import time

from hermes_minefield.privacy import arg_fingerprint, redact_text
from hermes_minefield.recorder.events import RecorderEvent, TOOL_PREPARED
from hermes_minefield.recorder.store import FlightRecorder


def test_recorder_retention_and_max_events():
    rec = FlightRecorder(retention_seconds=1, max_events=10, max_bytes=10_000_000, persist=False)
    for i in range(20):
        rec.record(RecorderEvent(type=TOOL_PREPARED, tool_name="t", ts=time.time()))
    assert rec.stats().events_in_memory <= 10
    time.sleep(1.1)
    rec.record(RecorderEvent(type=TOOL_PREPARED, tool_name="t", ts=time.time()))
    # old events trimmed by retention
    assert rec.stats().events_in_memory <= 10


def test_recorder_byte_ceiling():
    rec = FlightRecorder(retention_seconds=600, max_events=5000, max_bytes=2000, persist=False)
    for i in range(200):
        rec.record(
            RecorderEvent(
                type=TOOL_PREPARED,
                tool_name="search_files",
                tool_arg_fingerprint="x" * 32,
                extra={"pad": "y" * 64},
            )
        )
    assert rec.stats().approx_bytes <= 2000 + 500  # allow trim slack
    assert rec.stats().events_in_memory < 200


def test_secrets_redacted():
    text = "Authorization: Bearer ghp_abcdefghijklmnopqrstuvwx and api_key=sk-abc1234567890123456789"
    out = redact_text(text)
    assert "ghp_" not in out
    assert "sk-abc" not in out
    assert "Bearer ghp" not in out
    assert "[REDACTED]" in out


def test_arg_fingerprint_stable():
    assert arg_fingerprint({"a": 1, "b": 2}) == arg_fingerprint({"b": 2, "a": 1})
