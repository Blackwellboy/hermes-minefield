"""Minefield symptom matching adapter for incident triage.

The registry layout is owned by model-serving-minefield. This adapter consumes
only its versioned public API and never walks registry internals directly.
"""

from __future__ import annotations

from typing import Any


class TrapMatchError(RuntimeError):
    """Raised when the Minefield integration contract is unavailable or malformed."""


_NON_SERVING_CLASSIFICATIONS = {
    "HERMES_UI_ORCHESTRATION",
    "UI_RENDERING_BUG",
    "AGENT_TOOL_LOOP",
    "AGENT_LOOP",
    "EXPECTED_BEHAVIOUR",
    "HERMES_ORCHESTRATION_BUG",
    "TOOL_BUG",
}


def match_traps(
    *,
    classification: str,
    symptom: str,
    serving_failure: bool,
    stack: str | None = None,
    model: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return ranked canonical trap candidates from Minefield's public API.

    Text similarity is never treated as confirmation. Integration failures are
    raised as :class:`TrapMatchError` so callers can preserve the incident
    while recording that matching failed, rather than silently reporting zero
    candidates.
    """
    if not serving_failure and classification in _NON_SERVING_CLASSIFICATIONS:
        return []

    try:
        from minefield.api import match_symptom
    except Exception as exc:  # pragma: no cover - exercised through caller guard
        raise TrapMatchError(f"minefield.api.match_symptom unavailable: {type(exc).__name__}") from exc

    try:
        result = match_symptom(
            symptom or "",
            stack=stack,
            model=model,
            limit=max(1, int(limit)),
        )
    except Exception as exc:
        raise TrapMatchError(f"minefield symptom matching failed: {type(exc).__name__}") from exc

    if not isinstance(result, dict):
        raise TrapMatchError("minefield symptom matching returned a non-mapping result")

    raw_matches = result.get("matches")
    if raw_matches is None:
        raise TrapMatchError("minefield symptom matching result is missing 'matches'")
    if not isinstance(raw_matches, list):
        raise TrapMatchError("minefield symptom matching 'matches' is not a list")

    hits: list[dict[str, Any]] = []
    for match in raw_matches[: max(1, int(limit))]:
        if not isinstance(match, dict):
            continue
        trap_ids = match.get("trap_ids") or []
        if not isinstance(trap_ids, list) or not trap_ids:
            continue
        trap_id = str(trap_ids[0])
        hits.append(
            {
                "trap_id": trap_id,
                "title": str(match.get("title") or ""),
                "match": str(match.get("diagnosis_level") or "POSSIBLE_MATCH"),
                "score_hint": match.get("score"),
                "confirmation_check": match.get("confirmation_check"),
                "source_path": match.get("source_path"),
            }
        )
    return hits
