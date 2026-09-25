"""Review-gated GitHub issue operations.

Automatic upload is forbidden. Arbitrary repos are blocked unless allowlisted
or explicitly selected by the user in the same approval step.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .approval import ApprovalDecision, evaluate_approval
from .dedupe import map_github_state


@dataclass
class SubmitResult:
    submitted: bool
    url: str | None
    error: str | None
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
            f"ARBITRARY_REPO_SUBMISSION=BLOCKED: {repo} not in allowlist and not explicitly selected by user"
        )


def submit_issue(
    *,
    repo: str,
    title: str,
    body: str,
    allowlist: Sequence[str],
    user_selected_repo: bool,
    user_reply: str | None = None,
    cli_approve: bool = False,
    from_model: bool = False,
    dry_run: bool = True,
    token: str | None = None,
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
    token: str | None = None,
    linked_resolution: str | None = None,
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


_STOP = frozenset(
    {"with", "that", "this", "from", "have", "were", "into", "calls", "events", "window", "minefield"}
)


def dedupe_terms(title: str, *, limit: int = 5) -> list[str]:
    """Search terms derived from an already-sanitized title (alnum tokens, >= 4 chars)."""
    out: list[str] = []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9_]{3,}", title or ""):
        t = tok.lower()
        if t in _STOP or t in out or t.startswith("redacted"):
            continue
        out.append(t)
        if len(out) >= limit:
            break
    return out


def search_issues(
    *, repo: str, terms: Sequence[str], token: str | None = None, timeout: float = 10.0
) -> dict[str, Any]:
    """Read-only GitHub issue search. Sends only ``repo`` and ``terms``. Never raises."""
    if not terms:
        return {"ok": False, "error": "no_terms", "items": []}
    q = f"repo:{repo} is:issue in:title " + " ".join(terms)
    url = "https://api.github.com/search/issues?per_page=3&q=" + urllib.parse.quote(q)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "hermes-minefield"}
    tok = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = [
            {
                "number": it.get("number"),
                "title": str(it.get("title") or "")[:120],
                "state": it.get("state"),
                "html_url": it.get("html_url"),
            }
            for it in (data.get("items") or [])[:3]
            if isinstance(it, dict)
        ]
        return {"ok": True, "items": items}
    except Exception as e:
        return {"ok": False, "error": type(e).__name__, "items": []}


_ISSUE_URL_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/(\d+)$")


def parse_issue_url(url: str | None) -> tuple[str, int] | None:
    m = _ISSUE_URL_RE.match(url or "")
    return (m.group(1), int(m.group(2))) if m else None
