"""Generate sanitized GitHub issue drafts (never auto-submit)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from ..paths import drafts_dir
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
    target_repo: Optional[str] = None
    incident_id: Optional[str] = None
    body: str = ""

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
    target_repo: Optional[str] = None,
    environment: Optional[Mapping[str, Any]] = None,
) -> IssueDraft:
    classification = str(artifact.get("classification") or "UNKNOWN")
    symptom = str(artifact.get("observed_symptom") or "unspecified symptom")
    title = sanitize_issue_body(f"[minefield] {classification}: {symptom}")[:180]
    env = sanitize_packet({"environment": dict(environment or {})}).get("environment", {})
    draft = IssueDraft(
        title=title,
        summary=sanitize_issue_body(
            f"Incident classified as {classification}. "
            f"{artifact.get('likely_root_cause') or ''}"
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


def save_draft(draft: IssueDraft) -> Path:
    name = f"draft-{int(time.time())}-{draft.incident_id or 'anon'}.json"
    path = drafts_dir() / name
    path.write_text(json.dumps(asdict(draft), indent=2, sort_keys=True), encoding="utf-8")
    return path
