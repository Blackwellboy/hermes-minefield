"""/minefield wtf — freeze recorder + classify incident."""

from __future__ import annotations

import re
from typing import Any

from .. import verdict as V
from ..incident.analyze import analyze_events, render_incident
from ..incident.store import save_incident
from ..privacy import stable_hash
from ..recorder.store import get_recorder

_DURATION_RE = re.compile(r"^(\d+)\s*([smh])?$", re.I)


def parse_window(raw: str | None, default_seconds: float = 300.0) -> float:
    if not raw:
        return default_seconds
    raw = raw.strip()
    m = _DURATION_RE.match(raw)
    if not m:
        try:
            return float(raw)
        except ValueError:
            return default_seconds
    n = int(m.group(1))
    unit = (m.group(2) or "s").lower()
    if unit == "m":
        return float(n * 60)
    if unit == "h":
        return float(n * 3600)
    return float(n)


def incident_verdict(classification: str, event_count: int, *, truncated: bool = False) -> tuple[str, str]:
    """PASS only for aligned, complete evidence; no evidence is UNKNOWN, never clean."""
    if event_count == 0:
        return V.UNKNOWN, (
            "no recorder events in this window — nothing happened, or the recorder is not "
            "running in the Hermes process (is the plugin enabled?)"
        )
    if classification == "UNKNOWN":
        return V.UNKNOWN, "events recorded, but no classification fits them"
    if classification == "EXPECTED_BEHAVIOUR":
        if truncated:
            return V.UNKNOWN, "looks normal, but the window hit recorder_max_events so evidence is incomplete"
        return V.PASS, "recorded activity looks normal"
    note = " (window truncated at recorder_max_events)" if truncated else ""
    return V.FAIL, f"anomaly: {classification}{note}"


def should_skip_saving(classification: str, severity: str) -> bool:
    """Quiet or normal windows are not incidents; don't clutter `issues` with them."""
    return classification in {"UNKNOWN", "EXPECTED_BEHAVIOUR"} and severity == "LOW"


def run_wtf(
    *,
    window: str | None = None,
    session: str | None = None,
    save: bool | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Freeze + classify. ``save``: True/False forces; None saves only anomalies.
    ``persist=False`` (tests/legacy) never saves."""
    since = parse_window(window, default_seconds=300.0)
    sid_hash = None
    if session and session not in {"current", "all"}:
        sid_hash = stable_hash(session, n=16)

    rec = get_recorder()
    intro = f"yeah, that looked weird. freezing the last {since:.0f} seconds..."
    frozen = rec.freeze_detailed(since_seconds=since, session_id_hash=sid_hash)
    events = frozen.events
    artifact = analyze_events(
        events,
        session_id_hash=sid_hash,
        since_seconds=since,
        persist=False,
    )
    truncated = len(events) >= rec.max_events
    verdict, reason = incident_verdict(artifact.classification, len(events), truncated=truncated)
    if not persist:
        should_save = False
    elif save is None:
        should_save = not should_skip_saving(artifact.classification, artifact.severity)
    else:
        should_save = bool(save)
    if should_save:
        save_incident(artifact)
    # Concise UX; sources available in structured result for debug/tests.
    body = render_incident(artifact, saved=should_save)
    return {
        "ok": True,
        "verdict": verdict,
        "text": f"Minefield:\n{intro}\n\n{body}\n\n{V.line(verdict, reason)}",
        "incident_id": artifact.incident_id if should_save else None,
        "saved": should_save,
        "classification": artifact.classification,
        "severity": artifact.severity,
        "artifact": artifact.to_dict(),
        "event_count": len(events),
        "event_sources": {
            "memory": frozen.memory_count,
            "persisted": frozen.persisted_count,
            "deduped": frozen.deduped_count,
        },
    }
