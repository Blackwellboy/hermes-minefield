"""GitHub submission gates: no auto upload, model cannot approve, repo allowlist."""

from __future__ import annotations

import pytest

from hermes_minefield.issues.approval import evaluate_approval
from hermes_minefield.issues.draft import build_issue_draft
from hermes_minefield.issues.github_client import assert_repo_allowed, submit_issue
from hermes_minefield.privacy import looks_like_approval


ALLOW = ("Blackwellboy/model-serving-minefield", "NousResearch/hermes-agent")


def test_model_cannot_approve():
    d = evaluate_approval(user_reply="yes", from_model=True)
    assert d.approved is False
    assert "MODEL" in d.reason


def test_no_approval_blocks_submit():
    r = submit_issue(
        repo="NousResearch/hermes-agent",
        title="t",
        body="b",
        allowlist=ALLOW,
        user_selected_repo=True,
        user_reply="nope",
        dry_run=True,
    )
    assert r.submitted is False
    assert r.error and "blocked" in r.error


def test_explicit_approval_dry_run_ok():
    r = submit_issue(
        repo="NousResearch/hermes-agent",
        title="t",
        body="b",
        allowlist=ALLOW,
        user_selected_repo=True,
        user_reply="yes",
        dry_run=True,
    )
    assert r.submitted is True
    assert r.dry_run is True


def test_arbitrary_repo_blocked():
    with pytest.raises(PermissionError):
        assert_repo_allowed(
            "evil/exfil",
            allowlist=ALLOW,
            user_selected=False,
        )


def test_user_selected_repo_allowed_outside_allowlist():
    assert_repo_allowed("someone/else", allowlist=ALLOW, user_selected=True)


def test_hostile_model_yes_not_approval_helper():
    # looks_like_approval is strict; longer model prose should fail
    assert looks_like_approval("yes")
    assert not looks_like_approval("Sure, I approve submitting this to GitHub now.")


def test_draft_redacts_secrets(tmp_hermes_home):
    art = {
        "incident_id": "INC-TEST",
        "classification": "AGENT_TOOL_LOOP",
        "observed_symptom": "loop",
        "likely_root_cause": "loop",
        "actual_execution_counts": {},
        "repeated_call_counts": {},
        "severity": "HIGH",
        "confidence": "HIGH",
        "recommended_action": "break loop",
    }
    draft = build_issue_draft(
        artifact=art,
        target_repo="NousResearch/hermes-agent",
        environment={
            "base_url": "http://user:secretpass@10.0.0.5:8007/v1",
            "api_key": "sk-should-not-appear-in-body-XXXXXXXX",
        },
    )
    body = draft.body
    assert "secretpass" not in body
    assert "sk-should-not-appear" not in body
    assert "10.0.0.5" not in body or "[REDACTED" in body




def test_minefield_draft_matches_public_issue_form_shape(tmp_hermes_home):
    art = {
        "incident_id": "INC-TEST-FORM",
        "classification": "MODEL_SERVER_BUG",
        "observed_symptom": "streamed answer is blank",
        "likely_root_cause": "possible response-channel mismatch",
        "actual_execution_counts": {"total_executed": 3},
        "repeated_call_counts": {},
        "severity": "MEDIUM",
        "confidence": "MEDIUM",
        "recommended_action": "run the trap-specific paired control",
        "serving_failure": True,
        "known_trap_matches": [
            {
                "trap_id": "23",
                "title": "streaming answer lands in reasoning channel",
                "confirmation_check": "Compare streamed content and reasoning deltas.",
            }
        ],
    }
    draft = build_issue_draft(
        artifact=art,
        target_repo="Blackwellboy/model-serving-minefield",
        environment={"model": "example/model", "provider": "vllm"},
    )
    body = draft.body

    # These are the field labels used by the public Minefield trap form.
    for heading in (
        "### What broke",
        "### What you saw",
        "### What fixed it",
        "### What were you serving",
        "### Optional diagnostic evidence",
    ):
        assert heading in body

    assert '"trap_id": "23"' in body
    assert "Compare streamed content and reasoning deltas." in body
    assert '"model": "example/model"' in body
    assert '"provider": "vllm"' in body


def test_non_minefield_target_keeps_generic_bug_draft_shape(tmp_hermes_home):
    art = {
        "incident_id": "INC-TEST-GENERIC",
        "classification": "AGENT_TOOL_LOOP",
        "observed_symptom": "loop",
        "likely_root_cause": "loop",
        "actual_execution_counts": {},
        "repeated_call_counts": {},
        "severity": "HIGH",
        "confidence": "HIGH",
        "recommended_action": "break loop",
    }
    draft = build_issue_draft(
        artifact=art,
        target_repo="NousResearch/hermes-agent",
        environment={"provider": "openai"},
    )
    assert "## Summary" in draft.body
    assert "## Minimal repro" in draft.body
    assert "### What broke" not in draft.body


def test_closed_not_assumed_fixed():
    from hermes_minefield.issues.dedupe import map_github_state

    assert map_github_state("closed") == "CLOSED"
    assert map_github_state("closed", linked_resolution="FIXED") == "FIXED"
    assert map_github_state("open") == "OPEN"
