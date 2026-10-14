"""wtf saves anomalies only; contribute never matches itself (plan T1.6)."""

from __future__ import annotations

from hermes_minefield.commands.contribute import run_contribute
from hermes_minefield.commands.wtf import run_wtf
from hermes_minefield.incident.store import list_incidents
from hermes_minefield.paths import incidents_dir
from hermes_minefield.recorder.events import TOOL_EXECUTED, TOOL_PREPARED, RecorderEvent


def _saved_files():
    return sorted(incidents_dir().glob("INC-*.json"))


def _loop(rec, n=12):
    for _ in range(n):
        rec.record(RecorderEvent(type=TOOL_PREPARED, tool_name="search_files", tool_arg_fingerprint="same"))
        rec.record(
            RecorderEvent(
                type=TOOL_EXECUTED,
                tool_name="search_files",
                tool_arg_fingerprint="same",
                result_fingerprint="r",
            )
        )


def test_quiet_window_is_not_saved(tmp_hermes_home, fresh_recorder):
    out = run_wtf(window="1m")
    assert out["saved"] is False
    assert out["incident_id"] is None
    assert "not saved" in out["text"]
    assert "/minefield contribute" not in out["text"]
    assert _saved_files() == []


def test_quiet_window_saved_when_forced(tmp_hermes_home, fresh_recorder):
    out = run_wtf(window="1m", save=True)
    assert out["saved"] is True
    assert len(_saved_files()) == 1


def test_anomaly_is_saved_by_default(tmp_hermes_home, fresh_recorder):
    _loop(fresh_recorder)
    out = run_wtf(window="1m")
    assert out["classification"] == "AGENT_TOOL_LOOP"
    assert out["saved"] is True
    assert [p.stem for p in _saved_files()] == [out["incident_id"]]


def test_anomaly_not_saved_with_no_save(tmp_hermes_home, fresh_recorder):
    _loop(fresh_recorder)
    assert run_wtf(window="1m", save=False)["saved"] is False
    assert _saved_files() == []


def test_contribute_does_not_list_itself_as_duplicate(tmp_hermes_home, fresh_recorder):
    _loop(fresh_recorder)
    inc = run_wtf(window="1m")["incident_id"]
    assert [r["incident_id"] for r in list_incidents()] == [inc]
    out = run_contribute(incident_id=inc)
    assert "Possible duplicates" not in out["text"]
