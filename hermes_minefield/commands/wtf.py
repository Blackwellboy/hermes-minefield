""" /minefield wtf — freeze recorder + classify incident."""

from __future__ import annotations

import re
from typing import Any, Optional

from ..incident.analyze import analyze_events, render_incident
from ..privacy import stable_hash
from ..recorder.store import get_recorder


_DURATION_RE = re.compile(r"^(\d+)\s*([smh])?$", re.I)


def parse_window(raw: Optional[str], default_seconds: float = 300.0) -> float:
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


def run_wtf(
    *,
    window: Optional[str] = None,
    session: Optional[str] = None,
    persist: bool = True,
) -> dict[str, Any]:
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
        persist=persist,
    )
    # Concise UX; sources available in structured result for debug/tests.
    body = render_incident(artifact)
    return {
        "ok": True,
        "text": f"Minefield:\n{intro}\n\n{body}",
        "incident_id": artifact.incident_id,
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
