"""Local + optional GitHub issue dedupe (MATCH / POSSIBLE_MATCH / NO_MATCH)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence


@dataclass
class DedupeHit:
    match: str  # MATCH | POSSIBLE_MATCH | NO_MATCH
    issue_ref: Optional[str]
    title: str
    status: str
    reason: str


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]{4,}", (text or "").lower())}


def compare_signature(a: str, b: str) -> str:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return "NO_MATCH"
    inter = ta & tb
    union = ta | tb
    ratio = len(inter) / max(1, len(union))
    if ratio >= 0.55 and len(inter) >= 3:
        return "MATCH"
    if ratio >= 0.28 and len(inter) >= 2:
        return "POSSIBLE_MATCH"
    return "NO_MATCH"


def search_local(
    symptom: str,
    *,
    known: Sequence[Mapping[str, Any]],
    limit: int = 5,
) -> list[DedupeHit]:
    hits: list[DedupeHit] = []
    for row in known:
        title = str(row.get("title") or row.get("symptom") or row.get("observed_symptom") or "")
        kind = compare_signature(symptom, title)
        if kind == "NO_MATCH":
            continue
        hits.append(
            DedupeHit(
                match=kind,
                issue_ref=str(row.get("github") or row.get("issue_ref") or row.get("incident_id") or ""),
                title=title[:120],
                status=str(row.get("status") or row.get("github_status") or "UNKNOWN"),
                reason=f"token_overlap:{kind}",
            )
        )
    # Prefer MATCH over POSSIBLE
    hits.sort(key=lambda h: (0 if h.match == "MATCH" else 1, h.title))
    return hits[:limit]


def map_github_state(gh_state: str, *, linked_resolution: Optional[str] = None) -> str:
    """Closed ≠ FIXED unless resolution evidence exists."""
    s = (gh_state or "").lower()
    if s == "open":
        return "OPEN"
    if s in {"closed", "completed"}:
        if linked_resolution and linked_resolution.upper() in {"FIXED", "MERGED", "RESOLVED"}:
            return "FIXED"
        return "CLOSED"  # not assumed fixed
    return "UNKNOWN"
