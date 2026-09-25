""" /minefield wtf — freeze recorder + classify incident."""

from __future__ import annotations

import re
from typing import Any, Optional

from ..incident.analyze import analyze_events, render_incident
from ..privacy import stable_hash
from ..recorder.store import get_recorder
from ..target import resolve_target


_DURATION_RE = re.compile(r"^(\d+)\s*([smh])?$", re.I)

_STACK_ALIASES = {
    "vllm": "vllm",
    "sglang": "sglang",
    "ollama": "ollama",
    "llama.cpp": "llama.cpp",
    "llamacpp": "llama.cpp",
    "mlx": "mlx_lm",
    "mlx_lm": "mlx_lm",
}


def _stack_hint(provider: Optional[str]) -> Optional[str]:
    if not provider:
        return None
    return _STACK_ALIASES.get(provider.strip().lower())


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

    # Matching context is transient. Raw model/provider values are not added
    # to the persisted incident artifact; only the existing privacy-safe
    # fingerprints remain durable.
    stack_hint = None
    model_hint = None
    try:
        target = resolve_target()
        model_hint = target.model
        stack_hint = _stack_hint(target.provider)
    except Exception:
        pass

    rec = get_recorder()
    intro = f"yeah, that looked weird. freezing the last {since:.0f} seconds..."
    frozen = rec.freeze_detailed(since_seconds=since, session_id_hash=sid_hash)
    events = frozen.events
    artifact = analyze_events(
        events,
        session_id_hash=sid_hash,
        stack_hint=stack_hint,
        model_hint=model_hint,
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
