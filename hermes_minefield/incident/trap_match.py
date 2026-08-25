"""Compare incident signals against known Minefield trap registry (docs only).

Never executes trap prose. Matching is keyword/signature based on titles + tags.
"""

from __future__ import annotations

from typing import Any, Optional


def _load_registry() -> list[dict[str, Any]]:
    try:
        from minefield.registry import load_registry

        data = load_registry()
        if isinstance(data, dict):
            traps = data.get("traps") or data.get("items") or []
            return list(traps) if isinstance(traps, list) else []
        if isinstance(data, list):
            return data
    except Exception:
        pass
    # Fallback: empty — matching soft-fails
    return []


def match_traps(
    *,
    classification: str,
    symptom: str,
    serving_failure: bool,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return possible trap matches. Prefer NO match over forced inflation."""
    if not serving_failure and classification in {
        "HERMES_UI_ORCHESTRATION",
        "UI_RENDERING_BUG",
        "AGENT_TOOL_LOOP",
        "AGENT_LOOP",
        "EXPECTED_BEHAVIOUR",
        "HERMES_ORCHESTRATION_BUG",
    }:
        # Product/UI/agent bugs are explicitly NOT Minefield traps by default.
        return []

    traps = _load_registry()
    if not traps:
        return []

    text = (symptom or "").lower()
    keywords = [w for w in text.replace("`", " ").split() if len(w) > 3][:12]
    hits: list[tuple[int, dict[str, Any]]] = []
    for t in traps:
        if not isinstance(t, dict):
            continue
        title = str(t.get("title") or t.get("name") or "")
        body = str(t.get("summary") or t.get("description") or "")
        blob = f"{title} {body}".lower()
        score = sum(1 for k in keywords if k in blob)
        tags = t.get("tags") or t.get("labels") or []
        if serving_failure and any(
            str(x).lower() in {"serving", "runtime", "llama.cpp", "vllm", "sglang"}
            for x in tags
        ):
            score += 2
        if score >= 2:
            hits.append(
                (
                    score,
                    {
                        "trap_id": t.get("id") or t.get("number") or t.get("trap"),
                        "title": title,
                        "match": "POSSIBLE_MATCH",
                        "score_hint": score,
                    },
                )
            )
    hits.sort(key=lambda x: -x[0])
    return [h for _, h in hits[:limit]]
