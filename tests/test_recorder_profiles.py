"""One process, several profiles: Hermes 0.22's shared gateway scopes HERMES_HOME per turn
with a context variable, which the recorder's flusher thread does not inherit."""

from __future__ import annotations

import contextvars
import time

from hermes_minefield.recorder import store as store_mod
from hermes_minefield.recorder.events import RecorderEvent
from hermes_minefield.recorder.store import FlightRecorder, load_recent_persisted_events

PROFILE = contextvars.ContextVar("PROFILE", default="")


def _two_profiles(tmp_path, monkeypatch):
    def recorder_dir():
        d = tmp_path / (PROFILE.get() or "default") / "minefield" / "recorder"
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(store_mod, "recorder_dir", recorder_dir)
    monkeypatch.setattr(store_mod, "_home_override", lambda: PROFILE.get() or None)
    return recorder_dir


def _in_profile(name, fn, *args):
    ctx = contextvars.copy_context()
    ctx.run(PROFILE.set, name)
    return ctx.run(fn, *args)


def test_events_are_filed_under_the_profile_that_recorded_them(tmp_path, monkeypatch):
    _two_profiles(tmp_path, monkeypatch)
    r = FlightRecorder(persist=True)
    try:
        for i in range(3):
            _in_profile(
                "alpha",
                r.record,
                RecorderEvent(type="tool.executed", tool_name="a", event_id=f"a{i}", session_id_hash="sa"),
            )
            _in_profile(
                "beta",
                r.record,
                RecorderEvent(type="tool.executed", tool_name="b", event_id=f"b{i}", session_id_hash="sb"),
            )
        r.request_flush()
        deadline = time.time() + 5
        a_dir = tmp_path / "alpha" / "minefield" / "recorder"
        b_dir = tmp_path / "beta" / "minefield" / "recorder"
        while time.time() < deadline and not (list(a_dir.glob("events-*")) and list(b_dir.glob("events-*"))):
            time.sleep(0.05)
    finally:
        r.stop()
    a = [e.event_id for e in load_recent_persisted_events(directory=a_dir)]
    b = [e.event_id for e in load_recent_persisted_events(directory=b_dir)]
    assert sorted(a) == ["a0", "a1", "a2"]
    assert sorted(b) == ["b0", "b1", "b2"]
    assert not (tmp_path / "default").exists() or not list((tmp_path / "default").rglob("events-*"))


def test_freeze_and_current_session_never_cross_profiles(tmp_path, monkeypatch):
    _two_profiles(tmp_path, monkeypatch)
    r = FlightRecorder(persist=False)
    _in_profile(
        "alpha",
        r.record,
        RecorderEvent(type="tool.executed", tool_name="a", event_id="a1", session_id_hash="sa"),
    )
    _in_profile(
        "beta",
        r.record,
        RecorderEvent(type="tool.executed", tool_name="b", event_id="b1", session_id_hash="sb"),
    )
    a = _in_profile("alpha", r.freeze)
    b = _in_profile("beta", r.freeze)
    assert [e.event_id for e in a] == ["a1"]
    assert [e.event_id for e in b] == ["b1"]
    assert _in_profile("alpha", r.current_session_hash) == "sa"
    assert _in_profile("beta", r.current_session_hash) == "sb"
    assert _in_profile("alpha", r.stats).events_in_memory == 1
