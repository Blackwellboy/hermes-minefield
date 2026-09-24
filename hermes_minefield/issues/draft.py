"""Generate sanitized GitHub issue drafts (never auto-submit)."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..paths import atomic_write_text, drafts_dir
from .sanitize import sanitize_issue_body, sanitize_packet


@dataclass
class IssueDraft:
    title: str
    summary: str
    environment: dict[str, Any]
    minimal_repro: str
    expected: str
    observed: str
    evidence: str
    impact: str
    sanitization_notes: list[str] = field(default_factory=list)
    target_repo: str | None = None
    incident_id: str | None = None
    body: str = ""
    # Set when saved: what the human approves is exactly these bytes.
    body_sha256: str = ""
    user_selected_repo: bool = False

    def render_body(self) -> str:
        lines = [
            "## Summary",
            self.summary,
            "",
            "## Environment",
            "```json",
            json.dumps(self.environment, indent=2, sort_keys=True),
            "```",
            "",
            "## Minimal repro",
            self.minimal_repro,
            "",
            "## Expected",
            self.expected,
            "",
            "## Observed",
            self.observed,
            "",
            "## Evidence",
            self.evidence,
            "",
            "## Impact",
            self.impact,
            "",
            "## Sanitization notes",
            *[f"- {n}" for n in self.sanitization_notes],
        ]
        if self.incident_id:
            lines.extend(["", f"Local incident: `{self.incident_id}`"])
        return sanitize_issue_body("\n".join(lines))


def build_issue_draft(
    *,
    artifact: Mapping[str, Any],
    target_repo: str | None = None,
    environment: Mapping[str, Any] | None = None,
) -> IssueDraft:
    classification = str(artifact.get("classification") or "UNKNOWN")
    symptom = str(artifact.get("observed_symptom") or "unspecified symptom")
    title = sanitize_issue_body(f"[minefield] {classification}: {symptom}")[:180]
    env = sanitize_packet({"environment": dict(environment or {})}).get("environment", {})
    draft = IssueDraft(
        title=title,
        summary=sanitize_issue_body(
            f"Incident classified as {classification}. {artifact.get('likely_root_cause') or ''}"
        ),
        environment=env,
        minimal_repro=sanitize_issue_body(
            "Reproduce with flight-recorder hooks enabled, then `/minefield wtf`."
        ),
        expected=sanitize_issue_body("Stable tool prepare/execute accounting; no runaway loops."),
        observed=sanitize_issue_body(symptom),
        evidence=sanitize_issue_body(
            json.dumps(
                {
                    "actual_execution_counts": artifact.get("actual_execution_counts"),
                    "repeated_call_counts": artifact.get("repeated_call_counts"),
                    "severity": artifact.get("severity"),
                    "confidence": artifact.get("confidence"),
                },
                indent=2,
                sort_keys=True,
            )
        ),
        impact=sanitize_issue_body(str(artifact.get("recommended_action") or "")),
        sanitization_notes=[
            "secrets redacted",
            "no conversation text",
            "tool args omitted (fingerprints only)",
            "hosts/IPs redacted where present",
        ],
        target_repo=target_repo,
        incident_id=str(artifact.get("incident_id") or "") or None,
    )
    draft.body = draft.render_body()
    return draft


_DRAFT_ID_RE = re.compile(r"^draft-\d+-[A-Za-z0-9]{4,8}-(?:INC-\d{8}-[0-9A-F]{4,16}|anon)$")


def body_digest(title: str, body: str) -> str:
    return hashlib.sha256(f"{title}\n\n{body}".encode()).hexdigest()


def save_draft(draft: IssueDraft) -> Path:
    draft.body_sha256 = body_digest(draft.title, draft.body)
    name = f"draft-{int(time.time())}-{secrets.token_hex(2)}-{draft.incident_id or 'anon'}.json"
    path = drafts_dir() / name
    atomic_write_text(path, json.dumps(asdict(draft), indent=2, sort_keys=True))
    return path


class DraftError(ValueError):
    pass


def load_draft(draft_id: str) -> IssueDraft:
    """Load a saved draft and verify it is byte-identical to what was previewed."""
    draft_id = (draft_id or "").removesuffix(".json")
    if not _DRAFT_ID_RE.match(draft_id):
        raise DraftError(f"not a draft id: {draft_id!r}")
    path = drafts_dir() / f"{draft_id}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise DraftError(f"draft {draft_id} not found") from None
    except ValueError:
        raise DraftError(f"draft {draft_id} is corrupt") from None
    known = {f for f in IssueDraft.__dataclass_fields__}
    draft = IssueDraft(**{k: v for k, v in raw.items() if k in known})
    if not draft.body_sha256 or body_digest(draft.title, draft.body) != draft.body_sha256:
        raise DraftError(f"draft {draft_id} was modified after preview (sha256 mismatch); regenerate it")
    return draft
