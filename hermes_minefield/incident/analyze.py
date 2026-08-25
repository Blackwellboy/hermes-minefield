"""Build incident artifacts from frozen recorder windows (/minefield wtf)."""

from __future__ import annotations

import time
from typing import Optional, Sequence

from ..recorder.events import RecorderEvent
from .classify import ClassificationResult, classify, compute_signals
from .store import save_incident
from .trap_match import match_traps
from .types import IncidentArtifact


def analyze_events(
    events: Sequence[RecorderEvent],
    *,
    session_id_hash: Optional[str] = None,
    model_fingerprint: Optional[str] = None,
    runtime_fingerprint: Optional[str] = None,
    since_seconds: Optional[float] = None,
    persist: bool = True,
) -> IncidentArtifact:
    signals = compute_signals(events)
    result: ClassificationResult = classify(signals)
    tool = signals.dominant_tool or "tool"

    trap_matches = match_traps(
        classification=result.classification,
        symptom=result.observed_symptom,
        serving_failure=result.serving_failure,
    )

    status = "OBSERVED"
    if result.is_engineering_bug and not result.is_minefield_trap:
        status = "ENGINEERING_BUG"
    if trap_matches:
        status = "TRIAGED"

    artifact = IncidentArtifact(
        incident_id=IncidentArtifact.new_id(),
        timestamp=time.time(),
        session_id_hash=session_id_hash,
        model_fingerprint=model_fingerprint,
        runtime_fingerprint=runtime_fingerprint,
        event_window={
            "since_seconds": since_seconds,
            "event_count": len(events),
            "window_seconds": signals.window_seconds,
        },
        observed_symptom=result.observed_symptom,
        actual_execution_counts={
            "prepared": signals.prepared_by_tool,
            "requested": signals.requested_by_tool,
            "executed": signals.executed_by_tool,
            "total_prepared": signals.total_prepared,
            "total_executed": signals.total_executed,
            "dominant_tool": tool,
        },
        repeated_call_counts={
            "equivalent_executed": signals.equivalent_executed,
            "dominant_equivalent": signals.equivalent_executed.get(tool, 0),
        },
        timings={"window_seconds": signals.window_seconds},
        errors=[],
        classification=result.classification,
        severity=result.severity,
        known_trap_matches=trap_matches,
        known_issue_matches=[],
        likely_root_cause=result.likely_root_cause,
        confidence=result.confidence,
        recommended_action=result.recommended_action,
        privacy_redactions=["tool_args_omitted_by_default", "no_conversation_text"],
        content_included_by_user=False,
        status=status,
        serving_failure=result.serving_failure,
        is_minefield_trap=bool(trap_matches) and result.serving_failure,
        is_engineering_bug=result.is_engineering_bug,
        raw_event_count=len(events),
        notes=[
            "NOT_EVERY_BUG_IS_A_MINEFIELD_TRAP",
            f"api_errors={signals.total_api_errors}",
        ],
    )
    if persist:
        save_incident(artifact)
    return artifact


def render_incident(artifact: IncidentArtifact) -> str:
    exec_total = artifact.actual_execution_counts.get("total_executed", 0)
    prep_total = artifact.actual_execution_counts.get("total_prepared", 0)
    equiv = artifact.repeated_call_counts.get("dominant_equivalent", 0)
    trap_line = "NO"
    if artifact.known_trap_matches:
        m = artifact.known_trap_matches[0]
        trap_line = f"possible match {m.get('trap_id')} / {m.get('title')}"

    lines = [
        "MINEFIELD INCIDENT",
        "",
        f"ID: {artifact.incident_id}",
        f"Observed:",
        f"  {artifact.observed_symptom}",
        "",
        f"Actual executions: {exec_total}",
        f"Preparations:      {prep_total}",
        f"Repeated equivalent calls: {equiv}",
        "",
        f"Likely cause:",
        f"  {artifact.likely_root_cause}",
        "",
        f"Classification: {artifact.classification}",
        f"Severity:       {artifact.severity}",
        f"Serving failure: {'YES' if artifact.serving_failure else 'NO'}",
        f"Known Minefield trap: {trap_line}",
        f"Engineering bug (not trap): {'YES' if artifact.is_engineering_bug and not artifact.is_minefield_trap else 'NO'}",
        "",
        f"Recommendation:",
        f"  {artifact.recommended_action}",
        "",
        "Create local bug candidate?  (use: /minefield contribute)",
        "Draft GitHub issue?          (use: /minefield contribute --github)",
    ]
    return "\n".join(lines)
