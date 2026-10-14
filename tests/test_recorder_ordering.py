"""Equal wall-clock timestamps must not randomize observed chronology."""

import time

from hermes_minefield.recorder.events import RecorderEvent
from hermes_minefield.recorder.store import FlightRecorder


def test_equal_timestamp_preserves_append_order_after_restart(tmp_path):
    writer = FlightRecorder(directory=tmp_path)
    ts = time.time()
    writer.record(RecorderEvent(type="tool.executed", ts=ts, event_id="z", session_id_hash="first"))
    writer.record(RecorderEvent(type="tool.executed", ts=ts, event_id="a", session_id_hash="last"))
    assert [e.event_id for e in writer.freeze()] == ["z", "a"]
    writer.stop()
    reader = FlightRecorder(directory=tmp_path)
    assert [e.event_id for e in reader.freeze()] == ["z", "a"]
    assert reader.current_session_hash() == "last"
    reader.stop()
