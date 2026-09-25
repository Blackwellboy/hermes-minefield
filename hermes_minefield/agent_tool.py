"""Optional read-only agent tool: ``minefield_recent_incident``.

Lets a user ask "why did you just do that?" in natural language and the agent
pull the incident summary itself. Registered always (so the manifest's
``provides_tools`` matches), but only *offered to the model* when
``expose_agent_tool: true`` (Hermes ``check_fn`` gating).

Read-only: never saves incidents, never contributes, never touches the network.
Returns a summary only — no paths, hashes, or raw events.
"""

from __future__ import annotations

import json
from typing import Any

TOOL_NAME = "minefield_recent_incident"
TOOLSET = "minefield"

SCHEMA: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Explain what just happened in this Hermes session from Minefield's flight recorder: "
        "tool loops, failing tools, API errors, slow model, or normal activity. Read-only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "window": {
                "type": "string",
                "description": "How far back to look, e.g. '2m', '5m', '10m' (default 5m, max 1h).",
            }
        },
        "required": [],
    },
}

_SUMMARY_KEYS = (
    "classification",
    "severity",
    "confidence",
    "observed_symptom",
    "likely_root_cause",
    "recommended_action",
)


def available() -> bool:
    from .config import load_plugin_config

    return bool(load_plugin_config().expose_agent_tool)


def handler(args: dict | None = None, **_: Any) -> str:
    from .commands.wtf import parse_window, run_wtf

    try:
        window = str((args or {}).get("window") or "5m")
        if parse_window(window) > 3600:
            window = "1h"
        out = run_wtf(window=window, session="current", save=False)
        art = out.get("artifact") or {}
        counts = art.get("actual_execution_counts") or {}
        repeats = art.get("repeated_call_counts") or {}
        summary = {k: art.get(k) for k in _SUMMARY_KEYS}
        summary.update(
            verdict=out.get("verdict"),
            scope=out.get("scope"),
            window=window,
            events=out.get("event_count"),
            tool_executions=counts.get("total_executed"),
            tool_failures=counts.get("total_failed"),
            no_progress_streak=repeats.get("longest_no_progress_streak"),
        )
        return json.dumps(summary)
    except Exception as e:  # tools must return, not raise
        return json.dumps({"error": f"minefield unavailable ({type(e).__name__})"})
