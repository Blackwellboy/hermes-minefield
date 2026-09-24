"""Recorder hooks against Hermes's *real* kwargs (plan T1.1).

Payloads come from tests/fixtures/hermes_hook_payloads.json, which
tests/test_hermes_contract.py checks against Hermes's own fire sites.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hermes_minefield.incident.classify import classify, compute_signals
from hermes_minefield.recorder import hooks

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "hermes_hook_payloads.json").read_text())["hooks"]
SENTINELS = (
    "SENTINEL_ARG_VALUE",
    "SENTINEL_RESULT",
    "SENTINEL_ERRMSG",
    "SENTINEL_USER_MESSAGE",
    "SENTINEL_HISTORY",
    "SENTINEL_ASSISTANT",
    "SENTINEL_SYSTEM_PROMPT",
    "SENTINEL-HOST",
    "SENTINEL_SESSION_KEY",
)

HOOK_FUNCS = {
    "pre_tool_call": hooks.on_pre_tool_call,
    "post_tool_call": hooks.on_post_tool_call,
    "pre_llm_call": hooks.on_pre_llm_call,
    "post_llm_call": hooks.on_post_llm_call,
    "pre_api_request": hooks.on_pre_api_request,
    "post_api_request": hooks.on_post_api_request,
    "api_request_error": hooks.on_api_request_error,
    "on_session_start": hooks.on_session_start,
    "on_session_end": hooks.on_session_end,
    "on_session_finalize": hooks.on_session_finalize,
}


def payload(key: str, **override):
    p = copy.deepcopy(FIXTURE[key]["payload"])
    p.update(override)
    return p


def fire(key: str, **override):
    spec = FIXTURE[key]
    return HOOK_FUNCS[spec.get("hook", key)](**payload(key, **override))


def events(rec):
    return rec.freeze(include_persisted=False)


def of_type(rec, etype):
    return [e for e in events(rec) if e.type == etype]


def test_distinct_args_distinct_fingerprints(fresh_recorder):
    fire("pre_tool_call", args={"path": "a.py"})
    fire("pre_tool_call", args={"path": "b.py"})
    fire("pre_tool_call", args={"path": "a.py"})
    fps = [e.tool_arg_fingerprint for e in of_type(fresh_recorder, "tool.requested")]
    assert fps[0] != fps[1]
    assert fps[0] == fps[2]


def test_post_tool_call_ok(fresh_recorder):
    fire("post_tool_call")
    executed = of_type(fresh_recorder, "tool.executed")
    assert len(executed) == 1
    assert executed[0].success is True
    assert executed[0].wall_ms == 12.0
    assert len(of_type(fresh_recorder, "tool.completed")) == 1
    assert of_type(fresh_recorder, "tool.failed") == []


def test_post_tool_call_error_is_recorded_as_failure(fresh_recorder):
    fire("post_tool_call_error")
    executed = of_type(fresh_recorder, "tool.executed")
    assert executed[0].success is False
    failed = of_type(fresh_recorder, "tool.failed")
    assert len(failed) == 1
    assert failed[0].error_class == "tool_error"
    assert of_type(fresh_recorder, "tool.completed") == []


def test_post_api_request_fields(fresh_recorder):
    fire("post_api_request")
    (ev,) = of_type(fresh_recorder, "api.response")
    assert ev.wall_ms == pytest.approx(1500.0)
    assert ev.ttft_ms == pytest.approx(250.0)
    assert ev.content_len == 18
    assert ev.finish_reason == "tool_calls"
    assert ev.request_id_hash is not None
    assert ev.http_status is None
    assert ev.extra.get("tool_calls_requested") == 2


def test_post_api_request_without_first_chunk_leaves_ttft_unknown(fresh_recorder):
    p = payload("post_api_request")
    del p["first_chunk_at"]  # Hermes 0.21.0 does not send it
    hooks.on_post_api_request(**p)
    (ev,) = of_type(fresh_recorder, "api.response")
    assert ev.ttft_ms is None


def test_request_ids_correlate_across_api_hooks(fresh_recorder):
    fire("pre_api_request")
    fire("post_api_request")
    req, resp = of_type(fresh_recorder, "api.request")[0], of_type(fresh_recorder, "api.response")[0]
    assert req.request_id_hash and req.request_id_hash == resp.request_id_hash


def test_api_request_error_fields(fresh_recorder):
    fire("api_request_error")
    (ev,) = of_type(fresh_recorder, "api.error")
    assert ev.http_status == 503
    assert ev.error_class == "APIStatusError"
    assert ev.extra.get("retryable") is True
    assert ev.extra.get("retry_count") == 1


def test_post_llm_call_content_len(fresh_recorder):
    fire("post_llm_call")
    (ev,) = of_type(fresh_recorder, "turn.end")
    assert ev.content_len == len(FIXTURE["post_llm_call"]["payload"]["assistant_response"])


def test_session_end_records_completion_flags(fresh_recorder):
    fire("on_session_end", completed=False, interrupted=True)
    ev = [e for e in events(fresh_recorder) if e.extra.get("interrupted") is not None][0]
    assert ev.extra["completed"] is False
    assert ev.extra["interrupted"] is True


@pytest.mark.parametrize("key", sorted(k for k in FIXTURE if FIXTURE[k].get("hook", k) in HOOK_FUNCS))
def test_hooks_return_none_and_store_no_private_content(key, fresh_recorder):
    assert fire(key) is None  # pre_llm_call returns are injected into the prompt
    blob = json.dumps([e.to_dict() for e in events(fresh_recorder)])
    for s in SENTINELS:
        assert s not in blob, f"{key} leaked {s}"


def test_hooks_never_raise_on_garbage(fresh_recorder):
    for fn in HOOK_FUNCS.values():
        fn()  # no kwargs at all
        fn(tool_name=None, args=object(), result=object(), error=42, status_code="x", api_duration="nan?")


def test_distinct_reads_are_not_a_loop(fresh_recorder):
    """The review repro: 12 different read_file calls were classified AGENT_TOOL_LOOP/HIGH."""
    for i in range(12):
        fire("pre_tool_call", args={"path": f"file{i}.py"}, tool_call_id=f"c{i}")
        fire(
            "post_tool_call",
            args={"path": f"file{i}.py"},
            tool_call_id=f"c{i}",
            result=json.dumps({"content": f"body {i}"}),
        )
    result = classify(compute_signals(events(fresh_recorder)))
    assert result.classification != "AGENT_TOOL_LOOP"
