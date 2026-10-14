from hermes_minefield.recorder.events import RecorderEvent
from hermes_minefield.recorder.store import get_recorder, reset_recorder_for_tests


def test_profiles_cannot_share_memory_or_worker_destination(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "first"))
    first = reset_recorder_for_tests(persist=True)
    first.record(RecorderEvent(type="session.start", session_id_hash="first"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "second"))
    second = get_recorder(persist=True)
    assert second is not first
    assert second.current_session_hash() is None
    second.record(RecorderEvent(type="session.start", session_id_hash="second"))
    first.stop()
    second.stop()
    assert first._dir() == tmp_path / "first" / "minefield" / "recorder"
    assert second._dir() == tmp_path / "second" / "minefield" / "recorder"
    assert {e.session_id_hash for e in first.freeze()} == {"first"}
    assert {e.session_id_hash for e in second.freeze()} == {"second"}
