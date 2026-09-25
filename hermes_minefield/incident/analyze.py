"""Build incident artifacts from frozen recorder windows (/minefield wtf)."""

from __future__ import annotations

import time
from collections.abc import Sequence

from ..recorder.events import RecorderEvent
from .classify import ClassificationResult, classify, compute_signals
from .signals import percentile
from .store import save_incident
from .trap_match import TrapMatchError, match_traps
from .types import IncidentArtifact


def analyze_events(
    events: Sequence[RecorderEvent],
    *,
    session_id_hash: str | None = None,
    model_fingerprint: str | None = None,
    runtime_fingerprint: str | None = None,
    since_seconds: float | None = None,
    persist: bool = True,
    loop_streak_threshold: int | None = None,
) -> IncidentArtifact:
    signals = compute_signals(events)
    result: ClassificationResult = classify(signals, loop_streak_threshold=loop_streak_threshold)
    tool = signals.dominant_tool or "tool"

    trap_match_error = None
    try:
        trap_matches = match_traps(
            classification=result.classification,
            symptom=result.observed_symptom,
            serving_failure=result.serving_failure,
        )
    except TrapMatchError as exc:
        # Preserve the incident, but never let a broken integration contract
        # masquerade as "no Minefield trap matched".
        trap_matches = []
        trap_match_error = str(exc)

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
            "total_requested": signals.total_requested,
            "total_executed": signals.total_executed,
            "in_flight": signals.in_flight,
            "hung": signals.hung_by_tool,
            "undispatched": signals.undispatched,
            "failed": signals.failed_by_tool,
            "total_failed": signals.total_failed,
            "dominant_tool": tool,
        },
        repeated_call_counts={
            "equivalent_executed": signals.equivalent_executed,
            "dominant_equivalent": signals.equivalent_executed.get(tool, 0),
            "longest_no_progress_streak": signals.longest_streak,
            "streak_tool": signals.streak_tool,
            "guard_blocks": signals.guard_blocks,
        },
        timings={
            "window_seconds": signals.window_seconds,
            "api_responses": signals.api_responses,
            "api_p95_ms": percentile(signals.api_latency_ms, 0.95),
            "ttft_p95_ms": percentile(signals.api_ttft_ms, 0.95),
        },
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
            f"rule={result.rule}",
        ]
        + ([f"interrupted_turns={signals.interrupted_turns}"] if signals.interrupted_turns else [])
        + ([f"trap_match_error={trap_match_error}"] if trap_match_error else []),
    )
    if persist:
        save_incident(artifact)
    return artifact


def render_incident(artifact: IncidentArtifact, *, saved: bool = True) -> str:
    exec_total = artifact.actual_execution_counts.get("total_executed", 0)
    equiv = artifact.repeated_call_counts.get("dominant_equivalent", 0)
    dominant_tool = artifact.actual_execution_counts.get("dominant_tool") or ""
    streak = artifact.repeated_call_counts.get("longest_no_progress_streak", equiv)
    blocks = artifact.repeated_call_counts.get("guard_blocks")
    trap_line = "NO"
    if any(str(n).startswith("trap_match_error=") for n in artifact.notes or []):
        # A broken Minefield contract is missing evidence, not "no match".
        trap_line = "UNKNOWN (Minefield trap matching unavailable)"
    elif artifact.known_trap_matches:
        m = artifact.known_trap_matches[0]
        trap_line = f"possible match {m.get('trap_id')} / {m.get('title')}"

    lines = [
        "MINEFIELD INCIDENT",
        "",
        f"ID: {artifact.incident_id if saved else '(not saved)'}",
        "Observed:",
        f"  {artifact.observed_symptom}",
        "",
        f"ACTUAL_EXECUTIONS={exec_total}",
        f"REPEATED_EQUIVALENT_CALLS={equiv}",
        f"DOMINANT_TOOL={dominant_tool or 'unknown'}",
        f"TOOL_FAILURES={artifact.actual_execution_counts.get('total_failed', 0)}",
        f"NO_PROGRESS_STREAK={streak}",
        "GUARD_WARNINGS=unknown",
        f"GUARD_BLOCKS={'unknown' if blocks is None else blocks}",
        "",
        "Likely cause:",
        f"  {artifact.likely_root_cause}",
        "",
        f"Classification: {artifact.classification}",
        f"Severity:       {artifact.severity}",
        f"Serving failure: {'YES' if artifact.serving_failure else 'NO'}",
        f"Known Minefield trap: {trap_line}",
        f"Engineering bug (not trap): {'YES' if artifact.is_engineering_bug and not artifact.is_minefield_trap else 'NO'}",
        "",
        "Recommendation:",
        f"  {artifact.recommended_action}",
        "",
    ]
    if saved:
        lines += [
            "Create local bug candidate?  (use: /minefield contribute)",
            "Draft GitHub issue?          (use: /minefield contribute --github)",
        ]
    else:
        lines.append("(not saved — quiet or normal window; use --save to keep it)")
    return "\n".join(lines)
