"""Small local-only model interface. Arguments never grant authority."""

import json

from ..agent_tool import available
from .workspace import Workspace


def register(ctx):
    schemas = {
        "minefield_search": (
            "Search the local serving-trap registry; candidates are not confirmations.",
            {"query": {"type": "string", "maxLength": 500}},
            ["query"],
        ),
        "minefield_plan": (
            "Preview named catalogue checks. No requests, approval or execution.",
            {"probe_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 64}},
            ["probe_ids"],
        ),
        "minefield_privacy_status": ("Read contribution state; cannot change consent.", {}, []),
        "minefield_run_status": ("Read whether the native workflow has an executable job.", {}, []),
        "minefield_diagnose": (
            "Read a minimal current-session local diagnosis when trusted context is available.",
            {},
            [],
        ),
    }
    for name, (description, properties, required) in schemas.items():

        def handler(args=None, _name=name, **context):
            try:
                return json.dumps(invoke(_name, args or {}, context))
            except Exception:
                return json.dumps({"state": "UNAVAILABLE", "reason": "invalid_or_unavailable_local_request"})

        ctx.register_tool(
            name=name,
            toolset="minefield",
            schema={
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
            handler=handler,
            check_fn=available,
            description=description,
        )


def invoke(name, args, context):
    if type(args) is not dict:
        raise ValueError("object required")
    if name == "minefield_plan":
        if set(args) != {"probe_ids"}:
            raise ValueError("invalid plan arguments")
        return Workspace().preview(args["probe_ids"])
    if name == "minefield_search":
        from minefield.api import match_symptom

        if set(args) != {"query"} or type(args["query"]) is not str or not 1 <= len(args["query"]) <= 500:
            raise ValueError("invalid query")
        matches = match_symptom(args["query"], limit=3)
        # Query and operator paths never return to model context through this tool.
        return {
            "candidates": [
                {k: item.get(k) for k in ("trap_ids", "title", "diagnosis_level", "confirmation_check")}
                for item in matches.get("matches", [])[:3]
            ]
        }
    if args:
        raise ValueError("arguments not permitted")
    if name == "minefield_privacy_status":
        return {"sharing": "OFF", "recipient_configured": False, "host_consent_available": False}
    if name == "minefield_run_status":
        return {"state": "NOT_RUN", "reason": "native execution bridge unavailable"}
    if name == "minefield_diagnose":
        session = context.get("session_id")
        if not isinstance(session, str) or not session:
            return {"state": "UNAVAILABLE", "reason": "trusted session context missing"}
        from ..commands.wtf import run_wtf

        result = run_wtf(session=session, window="5m", save=False)
        return {
            "verdict": result.get("verdict", "UNKNOWN"),
            "classification": result.get("classification", "UNKNOWN"),
            "events": result.get("event_count", 0),
            "diagnosis_level": "candidate",
        }
    raise ValueError("unknown tool")
