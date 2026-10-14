"""Hermes-native features (plan T5.2-T5.4)."""

from __future__ import annotations

import json

import pytest

from hermes_minefield import agent_tool, auto_lite
from hermes_minefield.concurrency import ConcurrencyInfo
from hermes_minefield.config import load_plugin_config, set_plugin_id
from hermes_minefield.recorder.events import TOOL_EXECUTED, RecorderEvent


def _settings(home, body: str, plugin_id: str = "hermes-minefield"):
    (home / "config.yaml").write_text(
        f"model:\n  default: m\n  base_url: http://127.0.0.1:9/v1\n"
        f"plugins:\n  entries:\n    {plugin_id}:\n      settings:\n{body}"
    )


# --- T5.2: settings keyed by the id Hermes loaded us under -----------------


def test_settings_follow_ctx_plugin_id(tmp_hermes_home):
    _settings(tmp_hermes_home, "        lite_max_requests: 2\n", plugin_id="mf-catalog")
    try:
        assert load_plugin_config().lite_max_requests == 5  # unknown id: defaults
        set_plugin_id("mf-catalog")
        assert load_plugin_config().lite_max_requests == 2
    finally:
        set_plugin_id(None)


# --- T5.3: auto_lite --------------------------------------------------------


@pytest.fixture()
def fresh_auto_lite():
    auto_lite._reset_for_tests()
    yield
    auto_lite._reset_for_tests()


def test_auto_lite_off_by_default(tmp_hermes_home, fresh_auto_lite):
    started = []
    assert auto_lite.maybe_start(start_thread=started.append) is False
    assert started == []


def test_auto_lite_starts_once_per_process(tmp_hermes_home, fresh_auto_lite):
    _settings(tmp_hermes_home, "        auto_lite: true\n")
    started = []
    assert auto_lite.maybe_start(start_thread=started.append) is True
    assert auto_lite.maybe_start(start_thread=started.append) is False
    assert len(started) == 1


@pytest.mark.parametrize(("slots", "runs"), [(None, False), (1, False), (4, True)])
def test_auto_lite_only_on_multi_slot(tmp_hermes_home, monkeypatch, slots, runs):
    _settings(tmp_hermes_home, "        auto_lite: true\n")
    monkeypatch.setattr(
        "hermes_minefield.concurrency.probe_concurrency",
        lambda url, **kw: ConcurrencyInfo(slots, slots == 1, "test", f"slots={slots}"),
    )
    calls = []
    monkeypatch.setattr("hermes_minefield.commands.check.run_check", lambda **kw: calls.append(1) or {})
    auto_lite._run()
    assert bool(calls) is runs


def test_session_start_hook_is_instant(tmp_hermes_home, fresh_auto_lite, monkeypatch):
    import time

    _settings(tmp_hermes_home, "        auto_lite: true\n")
    monkeypatch.setattr(auto_lite, "_run", lambda: time.sleep(5))  # a slow check
    t0 = time.perf_counter()
    auto_lite.maybe_start()  # real daemon thread
    assert time.perf_counter() - t0 < 0.5


# --- T5.4: read-only agent tool --------------------------------------------


def test_tool_hidden_unless_enabled(tmp_hermes_home):
    assert agent_tool.available() is False
    _settings(tmp_hermes_home, "        expose_agent_tool: true\n")
    assert agent_tool.available() is True


def test_tool_returns_summary_only(tmp_hermes_home, fresh_recorder):
    for _ in range(6):
        fresh_recorder.record(
            RecorderEvent(
                type=TOOL_EXECUTED,
                tool_name="read_file",
                tool_arg_fingerprint="abc",
                result_fingerprint="def",
            )
        )
    out = json.loads(agent_tool.handler({"window": "10m"}))
    assert out["classification"] == "AGENT_TOOL_LOOP"
    assert out["verdict"] == "FAIL"
    assert out["no_progress_streak"] == 6
    blob = json.dumps(out)
    assert "abc" not in blob and "def" not in blob and str(tmp_hermes_home) not in blob


def test_tool_is_read_only(tmp_hermes_home, fresh_recorder):
    from hermes_minefield.paths import incidents_dir

    for _ in range(6):
        fresh_recorder.record(
            RecorderEvent(
                type=TOOL_EXECUTED, tool_name="read_file", tool_arg_fingerprint="a", result_fingerprint="r"
            )
        )
    agent_tool.handler({})
    assert list(incidents_dir().glob("INC-*.json")) == []


def test_tool_never_raises(monkeypatch):
    def boom(**kw):
        raise RuntimeError("x")

    monkeypatch.setattr("hermes_minefield.commands.wtf.run_wtf", boom)
    assert "error" in json.loads(agent_tool.handler({"window": "5m"}))
