"""Contribution workflow hardening (plan T4.1-T4.5)."""

from __future__ import annotations

import io
import json
import urllib.parse

import pytest

from hermes_minefield.commands.contribute import run_contribute
from hermes_minefield.commands.dispatch import slash_result
from hermes_minefield.commands.issues import run_issues
from hermes_minefield.incident.analyze import analyze_events
from hermes_minefield.incident.store import load_incident
from hermes_minefield.paths import drafts_dir
from hermes_minefield.recorder.events import TOOL_EXECUTED, RecorderEvent

REPO = "NousResearch/hermes-agent"


@pytest.fixture()
def loop_incident(tmp_hermes_home):
    events = [
        RecorderEvent(
            type=TOOL_EXECUTED, tool_name="read_file", tool_arg_fingerprint="a", result_fingerprint="r"
        )
        for _ in range(8)
    ]
    return analyze_events(events, persist=True).incident_id


class FakeGitHub:
    """Stands in for urllib.request.urlopen; records every request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        body = self.responses.pop(0)
        if isinstance(body, Exception):
            raise body
        return io.BytesIO(json.dumps(body).encode())


@pytest.fixture()
def github(monkeypatch):
    def install(*responses):
        fake = FakeGitHub(responses)
        monkeypatch.setattr("hermes_minefield.issues.github_client.urllib.request.urlopen", fake)
        return fake

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    return install


def _draft(incident_id):
    out = run_contribute(incident_id=incident_id, github=True)
    assert out["target_repo"] == REPO, out["text"]
    return out


# --- T4.3 -------------------------------------------------------------------


def test_unknown_incident_is_an_error_not_a_substitute(loop_incident):
    out = run_contribute(incident_id="INC-20000101-FFFF")
    assert out["ok"] is False
    assert "not found" in out["text"] and loop_incident in out["text"]


def test_omitted_incident_says_which_one_it_used(loop_incident):
    out = run_contribute()
    assert f"using latest incident {loop_incident}" in out["text"]


# --- T4.2 -------------------------------------------------------------------


def test_submit_draft_sends_exactly_the_previewed_bytes(loop_incident, github):
    preview = _draft(loop_incident)
    fake = github({"html_url": f"https://github.com/{REPO}/issues/42"})
    out = run_contribute(submit_draft=preview["draft_id"], approve=True, dry_run=False)
    assert out["submit"]["submitted"] is True
    sent = json.loads(fake.requests[0].data)
    assert sent["body"] == preview["draft_body"]
    assert out["body_sha256"] == preview["body_sha256"]


def test_tampered_draft_is_refused(loop_incident, github):
    preview = _draft(loop_incident)
    path = drafts_dir() / f"{preview['draft_id']}.json"
    data = json.loads(path.read_text())
    data["body"] += "\nsneaky extra line"
    path.write_text(json.dumps(data))
    fake = github()
    out = run_contribute(submit_draft=preview["draft_id"], approve=True, dry_run=False)
    assert out["ok"] is False and "sha256 mismatch" in out["text"]
    assert fake.requests == []


@pytest.mark.parametrize("bad", ["../../etc/passwd", "draft-1-../x", "nope"])
def test_bad_draft_ids_are_rejected(tmp_hermes_home, bad):
    assert run_contribute(submit_draft=bad, approve=True)["ok"] is False


def test_submit_draft_without_approval_does_nothing(loop_incident, github):
    preview = _draft(loop_incident)
    fake = github()
    out = run_contribute(submit_draft=preview["draft_id"])
    assert "Not submitted" in out["text"] and fake.requests == []


# --- T4.1 -------------------------------------------------------------------


def test_real_submit_links_incident_and_issues_refresh_works(loop_incident, github):
    preview = _draft(loop_incident)
    github({"html_url": f"https://github.com/{REPO}/issues/42"}, {"state": "open", "title": "t"})
    out = run_contribute(submit_draft=preview["draft_id"], approve=True, dry_run=False)
    assert out["linked"] == {"repo": REPO, "number": 42, "html_url": f"https://github.com/{REPO}/issues/42"}
    inc = load_incident(loop_incident)
    assert inc["status"] == "SUBMITTED" and inc["github"]["number"] == 42
    issues = run_issues(refresh=True)
    assert issues["items"][0]["status"] == "OPEN"
    assert "[OPEN]" in issues["items"][0]["github"]


def test_dry_run_does_not_link(loop_incident, github):
    preview = _draft(loop_incident)
    run_contribute(submit_draft=preview["draft_id"], approve=True, dry_run=True)
    assert load_incident(loop_incident)["status"] != "SUBMITTED"


# --- T4.4 -------------------------------------------------------------------


def test_remote_dedupe_is_off_by_default(loop_incident, github):
    fake = github()
    out = _draft(loop_incident)
    assert fake.requests == []
    assert "Searching GitHub" not in out["text"]


def test_remote_dedupe_prints_exactly_what_it_sends(loop_incident, github):
    fake = github({"items": [{"number": 7, "title": "loop in read_file", "state": "open", "html_url": "u"}]})
    out = run_contribute(incident_id=loop_incident, github=True, remote_dedupe=True)
    terms = out["remote_dedupe"]["terms"]
    assert f"Searching GitHub ({REPO}) for these sanitized terms: {' '.join(terms)}" in out["text"]
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(fake.requests[0].full_url).query)["q"][0]
    assert q == f"repo:{REPO} is:issue in:title " + " ".join(terms)
    assert "#7 [open] loop in read_file" in out["text"]


def test_remote_dedupe_failure_is_not_an_error(loop_incident, github):
    github(TimeoutError())
    out = run_contribute(incident_id=loop_incident, github=True, remote_dedupe=True)
    assert out["ok"] is True and "(remote dedupe unavailable)" in out["text"]


# --- T4.5 -------------------------------------------------------------------


def test_chat_cannot_really_submit_by_default(loop_incident, github):
    preview = _draft(loop_incident)
    fake = github()
    out = slash_result(f"contribute --submit-draft {preview['draft_id']} --i-approve-submit --submit")
    assert out["submit"]["error"] == "blocked:chat_submit_disabled"
    assert "CLI-only" in out["text"] and fake.requests == []


def test_chat_dry_run_is_allowed(loop_incident, github):
    preview = _draft(loop_incident)
    out = slash_result(f"contribute --submit-draft {preview['draft_id']} --i-approve-submit")
    assert out["submit"]["dry_run"] is True and out["submit"]["submitted"] is True


def test_chat_submit_when_explicitly_enabled(loop_incident, github, tmp_hermes_home):
    (tmp_hermes_home / "config.yaml").write_text(
        "plugins:\n  entries:\n    hermes-minefield:\n      settings:\n        allow_submit_from_chat: true\n"
    )
    preview = _draft(loop_incident)
    github({"html_url": f"https://github.com/{REPO}/issues/5"})
    out = slash_result(f"contribute --submit-draft {preview['draft_id']} --i-approve-submit --submit")
    assert out["submit"]["submitted"] is True and out["submit"]["dry_run"] is False


def test_model_can_still_never_approve(loop_incident, github):
    preview = _draft(loop_incident)
    fake = github()
    out = run_contribute(submit_draft=preview["draft_id"], user_reply="yes", from_model=True, dry_run=False)
    assert out["submit"]["error"] == "blocked:MODEL_CAN_APPROVE_UPLOAD=NO"
    assert fake.requests == []
