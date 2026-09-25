"""Cross-repo contract tests for Hermes ↔ Model Serving Minefield."""

from __future__ import annotations

from pathlib import Path

import yaml

from hermes_minefield.commands.wtf import _stack_hint
from hermes_minefield.incident import analyze as analyze_mod
from hermes_minefield.incident.trap_match import TrapMatchError, match_traps
from hermes_minefield.privacy import arg_fingerprint
from hermes_minefield.recorder import hooks
from hermes_minefield.recorder.events import API_ERROR, RecorderEvent


def test_minefield_02_exports_match_symptom():
    from minefield.api import match_symptom

    assert callable(match_symptom)


def test_real_adapter_returns_known_trap_23():
    hits = match_traps(
        classification="MODEL_SERVER_BUG",
        symptom="answer lands in the reasoning channel when streaming",
        serving_failure=True,
        limit=5,
    )
    assert hits, "known Minefield symptom produced no adapter matches"
    assert any(str(hit["trap_id"]).lstrip("0") == "23" for hit in hits)
    assert all(hit["match"] != "CONFIRMED" for hit in hits)


def test_real_adapter_nonsense_returns_no_match():
    hits = match_traps(
        classification="MODEL_SERVER_BUG",
        symptom="zzqxv qqzzw",
        serving_failure=True,
    )
    assert hits == []


def test_non_serving_agent_loop_is_not_inflated_into_minefield_trap():
    hits = match_traps(
        classification="AGENT_TOOL_LOOP",
        symptom="repeated read_file calls",
        serving_failure=False,
    )
    assert hits == []




def test_matcher_forwards_stack_and_model_without_persisting_them(monkeypatch):
    import minefield.api as minefield_api

    seen = {}

    def fake_match(symptom, **kwargs):
        seen["symptom"] = symptom
        seen.update(kwargs)
        return {"matches": []}

    monkeypatch.setattr(minefield_api, "match_symptom", fake_match)
    hits = match_traps(
        classification="MODEL_SERVER_BUG",
        symptom="streamed content is empty",
        serving_failure=True,
        stack="vllm",
        model="example/model",
        limit=3,
    )
    assert hits == []
    assert seen["stack"] == "vllm"
    assert seen["model"] == "example/model"
    assert seen["limit"] == 3


def test_analyzer_forwards_transient_context_and_renders_confirmation(monkeypatch):
    seen = {}

    def fake_matcher(**kwargs):
        seen.update(kwargs)
        return [
            {
                "trap_id": "23",
                "title": "streaming answer lands in reasoning channel",
                "match": "POSSIBLE_RELATED_TRAP",
                "confirmation_check": "Compare streamed content and reasoning deltas.",
            }
        ]

    monkeypatch.setattr(analyze_mod, "match_traps", fake_matcher)
    events = [
        RecorderEvent(type=API_ERROR),
        RecorderEvent(type=API_ERROR),
        RecorderEvent(type=API_ERROR),
    ]
    artifact = analyze_mod.analyze_events(
        events,
        stack_hint="vllm",
        model_hint="example/model",
        persist=False,
    )

    assert seen["stack"] == "vllm"
    assert seen["model"] == "example/model"
    # Raw hints are transient and are not fields in the persisted incident.
    payload = artifact.to_dict()
    assert "stack_hint" not in payload
    assert "model_hint" not in payload

    rendered = analyze_mod.render_incident(artifact)
    assert "Top-match confirmation check:" in rendered
    assert "Compare streamed content and reasoning deltas." in rendered


def test_only_recognized_serving_providers_become_stack_hints():
    assert _stack_hint("vllm") == "vllm"
    assert _stack_hint("SGLang") == "sglang"
    assert _stack_hint("llamacpp") == "llama.cpp"
    assert _stack_hint("openai") is None
    assert _stack_hint("custom") is None
    assert _stack_hint(None) is None


def test_current_hermes_args_payload_is_fingerprinted(fresh_recorder):
    hooks.on_pre_tool_call(tool_name="read_file", args={"path": "A.txt"})
    hooks.on_post_tool_call(tool_name="read_file", args={"path": "A.txt"}, result="ok")
    hooks.on_pre_tool_call(tool_name="read_file", args={"path": "B.txt"})
    hooks.on_post_tool_call(tool_name="read_file", args={"path": "B.txt"}, result="ok")

    events = fresh_recorder.freeze(since_seconds=60)
    prepared = [e for e in events if e.type == "tool.prepared"]
    executed = [e for e in events if e.type == "tool.executed"]

    expected_a = arg_fingerprint({"path": "A.txt"})
    expected_b = arg_fingerprint({"path": "B.txt"})
    assert expected_a != expected_b
    assert [e.tool_arg_fingerprint for e in prepared] == [expected_a, expected_b]
    assert [e.tool_arg_fingerprint for e in executed] == [expected_a, expected_b]


def test_legacy_params_keyword_still_fingerprints(fresh_recorder):
    hooks.on_pre_tool_call(tool_name="read_file", params={"path": "legacy.txt"})
    events = fresh_recorder.freeze(since_seconds=60)
    prepared = [e for e in events if e.type == "tool.prepared"]
    assert prepared[0].tool_arg_fingerprint == arg_fingerprint({"path": "legacy.txt"})


def test_matcher_failure_is_visible_not_silent(monkeypatch):
    def broken_matcher(**_kwargs):
        raise TrapMatchError("contract unavailable")

    monkeypatch.setattr(analyze_mod, "match_traps", broken_matcher)
    events = [
        RecorderEvent(type=API_ERROR),
        RecorderEvent(type=API_ERROR),
        RecorderEvent(type=API_ERROR),
    ]
    artifact = analyze_mod.analyze_events(events, persist=False)

    assert artifact.serving_failure is True
    assert artifact.known_trap_matches == []
    assert any(
        note.startswith("trap_match_error=contract unavailable")
        for note in artifact.notes
    )


def test_manifest_uses_canonical_provides_hooks():
    root = Path(__file__).resolve().parents[1]
    manifest = yaml.safe_load((root / "plugin.yaml").read_text(encoding="utf-8"))
    assert "provides_hooks" in manifest
    assert "hooks" not in manifest
    assert set(manifest["provides_hooks"]) == {
        "pre_tool_call",
        "post_tool_call",
        "pre_llm_call",
        "post_llm_call",
        "pre_api_request",
        "post_api_request",
        "api_request_error",
        "on_session_start",
        "on_session_end",
        "on_session_finalize",
    }
