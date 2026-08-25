"""Review-gated GitHub issue operations.

Automatic upload is forbidden. Arbitrary repos are blocked unless allowlisted
or explicitly selected by the user in the same approval step.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from .approval import ApprovalDecision, evaluate_approval
from .dedupe import map_github_state


@dataclass
class SubmitResult:
    submitted: bool
    url: Optional[str]
    error: Optional[str]
    dry_run: bool


def assert_repo_allowed(
    repo: str,
    *,
    allowlist: Sequence[str],
    user_selected: bool,
) -> None:
    repo = (repo or "").strip()
    if not repo or "/" not in repo:
        raise ValueError("target repo must look like owner/name")
    if user_selected:
        return
    if repo not in set(allowlist):
        raise PermissionError(
            f"ARBITRARY_REPO_SUBMISSION=BLOCKED: {repo} not in allowlist "
            f"and not explicitly selected by user"
        )


def submit_issue(
    *,
    repo: str,
    title: str,
    body: str,
    allowlist: Sequence[str],
    user_selected_repo: bool,
    user_reply: Optional[str] = None,
    cli_approve: bool = False,
    from_model: bool = False,
    dry_run: bool = True,
    token: Optional[str] = None,
) -> SubmitResult:
    assert_repo_allowed(repo, allowlist=allowlist, user_selected=user_selected_repo)
    decision: ApprovalDecision = evaluate_approval(
        user_reply=user_reply, cli_flag=cli_approve, from_model=from_model
    )
    if not decision.approved:
        return SubmitResult(False, None, f"blocked:{decision.reason}", dry_run=True)

    if dry_run:
        return SubmitResult(True, f"dry-run://{repo}/issues#preview", None, dry_run=True)

    tok = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not tok:
        return SubmitResult(False, None, "missing_github_token", dry_run=False)

    url = f"https://api.github.com/repos/{repo}/issues"
    payload = json.dumps({"title": title, "body": body}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
            "User-Agent": "hermes-minefield",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return SubmitResult(True, data.get("html_url"), None, dry_run=False)
    except urllib.error.HTTPError as e:
        return SubmitResult(False, None, f"http_{e.code}", dry_run=False)
    except Exception as e:
        return SubmitResult(False, None, type(e).__name__, dry_run=False)


def refresh_issue_status(
    *,
    repo: str,
    number: int,
    token: Optional[str] = None,
    linked_resolution: Optional[str] = None,
) -> dict[str, Any]:
    tok = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    url = f"https://api.github.com/repos/{repo}/issues/{int(number)}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "hermes-minefield"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        state = map_github_state(str(data.get("state") or ""), linked_resolution=linked_resolution)
        return {
            "ok": True,
            "state_raw": data.get("state"),
            "status": state,
            "title": data.get("title"),
            "html_url": data.get("html_url"),
            "closed_assumed_fixed": False,
        }
    except Exception as e:
        return {"ok": False, "error": type(e).__name__, "status": "UNKNOWN"}
