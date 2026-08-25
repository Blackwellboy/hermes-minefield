"""Classification → SAFE GitHub target recommendation tests."""

from __future__ import annotations

from hermes_minefield.issues.routing import (
    REPO_HERMES,
    REPO_LLAMA,
    REPO_MINEFIELD,
    recommend_target_repo,
    resolve_contribute_target,
)


def test_hermes_ui_bug_recommends_hermes():
    r = recommend_target_repo(classification="HERMES_UI_ORCHESTRATION", is_engineering_bug=True)
    assert r.recommended_repo == REPO_HERMES
    assert r.user_selection_required is False


def test_agent_tool_loop_recommends_hermes():
    r = recommend_target_repo(classification="AGENT_TOOL_LOOP", is_engineering_bug=True)
    assert r.recommended_repo == REPO_HERMES


def test_llama_runtime_bug_recommends_llama():
    r = recommend_target_repo(classification="MODEL_SERVER_BUG", serving_failure=True)
    assert r.recommended_repo == REPO_LLAMA


def test_runtime_bug_recommends_llama():
    r = recommend_target_repo(classification="RUNTIME_BUG", serving_failure=True)
    assert r.recommended_repo == REPO_LLAMA


def test_minefield_candidate_recommends_minefield():
    r = recommend_target_repo(
        classification="POSSIBLE_NEW_MINEFIELD_CANDIDATE",
        serving_failure=True,
        is_minefield_trap=True,
    )
    assert r.recommended_repo == REPO_MINEFIELD


def test_unknown_asks_user():
    r = recommend_target_repo(classification="UNKNOWN")
    assert r.recommended_repo is None
    assert r.user_selection_required is True


def test_configuration_asks_user():
    r = recommend_target_repo(classification="CONFIGURATION_ERROR")
    assert r.recommended_repo is None
    assert r.user_selection_required is True


def test_explicit_repo_allowlisted():
    out = resolve_contribute_target(
        artifact={"classification": "UNKNOWN"},
        explicit_repo=REPO_HERMES,
        user_selected_repo=True,
    )
    assert out["can_draft"] is True
    assert out["target_repo"] == REPO_HERMES
    assert out["reason"] == "explicit_user_repo"


def test_hostile_model_output_cannot_alter_recommendation():
    r = recommend_target_repo(
        classification="HERMES_UI_ORCHESTRATION",
        model_suggested_repo="evil/exfil-repo",
    )
    assert r.recommended_repo == REPO_HERMES
    # Even when classification is unknown, model suggestion is ignored
    r2 = recommend_target_repo(
        classification="UNKNOWN",
        model_suggested_repo=REPO_HERMES,
    )
    assert r2.recommended_repo is None
    assert r2.user_selection_required is True

    out = resolve_contribute_target(
        artifact={"classification": "UNKNOWN"},
        model_suggested_repo="evil/exfil",
    )
    assert out["can_draft"] is False
    assert out["target_repo"] is None
    assert out["user_selection_required"] is True


def test_contribute_github_hermes_ui_routes(tmp_hermes_home):
    from hermes_minefield.commands.contribute import run_contribute
    from hermes_minefield.incident.analyze import analyze_events
    from hermes_minefield.recorder.events import RecorderEvent, TOOL_EXECUTED, TOOL_PREPARED

    events = [
        RecorderEvent(type=TOOL_PREPARED, tool_name="search_files", tool_arg_fingerprint="a")
        for _ in range(20)
    ]
    events.append(
        RecorderEvent(
            type=TOOL_EXECUTED, tool_name="search_files", tool_arg_fingerprint="a", success=True
        )
    )
    art = analyze_events(events, persist=True)
    out = run_contribute(incident_id=art.incident_id, github=True, dry_run=True)
    assert out["recommended_repo"] == REPO_HERMES
    assert out["target_repo"] == REPO_HERMES
    assert "NousResearch/hermes-agent" in out["text"]
    assert "model-serving-minefield" not in out["text"].split("target:")[1].split("\n")[0]


def test_contribute_unknown_requires_selection(tmp_hermes_home):
    from hermes_minefield.commands.contribute import run_contribute
    from hermes_minefield.incident.store import save_incident
    from hermes_minefield.incident.types import IncidentArtifact
    import time

    art = IncidentArtifact(
        incident_id="INC-TEST-UNK",
        timestamp=time.time(),
        session_id_hash=None,
        model_fingerprint=None,
        runtime_fingerprint=None,
        event_window={},
        observed_symptom="unclear",
        actual_execution_counts={},
        repeated_call_counts={},
        timings={},
        errors=[],
        classification="UNKNOWN",
        severity="LOW",
        likely_root_cause="unclear",
        recommended_action="ask",
    )
    save_incident(art)
    out = run_contribute(incident_id="INC-TEST-UNK", github=True)
    assert out.get("user_selection_required") is True
    assert out.get("target_repo") is None
    assert "USER_SELECTION_REQUIRED=YES" in out["text"]
