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


def test_closed_not_assumed_fixed():
    from hermes_minefield.issues.dedupe import map_github_state

    assert map_github_state("closed") == "CLOSED"
    assert map_github_state("closed", linked_resolution="FIXED") == "FIXED"
    assert map_github_state("open") == "OPEN"
