from hermes_minefield.recorder.events import RecorderEvent
from hermes_minefield.recorder.store import FlightRecorder


def test_stalled_persistence_is_bounded_and_loss_is_visible(tmp_path, monkeypatch):
    recorder = FlightRecorder(directory=tmp_path, persist=True, max_events=100, max_bytes=65536)
    # Simulate a disk worker that cannot drain; hooks must still remain bounded.
    monkeypatch.setattr(recorder, "_start_flusher", lambda: None)
    for _ in range(1000):
        recorder.record(RecorderEvent(type="session.start"))
    stats = recorder.stats()
    assert len(recorder._pending) <= 100
    assert recorder._pending_bytes <= 65536
    assert stats.persistence_dropped >= 900
    recorder.stop()
