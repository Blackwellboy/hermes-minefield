"""Full Minefield Doctor — explicit only, with single-slot guard."""

from __future__ import annotations

from typing import Any, Optional

from ..concurrency import doctor_guard_message, probe_concurrency, requires_doctor_confirm
from ..render import render_doctor_summary
from ..target import resolve_target


def run_doctor(
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    yes: bool = False,
    max_requests: Optional[int] = None,
    detect: bool = True,
) -> dict[str, Any]:
    # Resolve target + concurrency guard BEFORE importing Minefield so a
    # blocked single-slot run never depends on minefield being importable,
    # and never issues Doctor requests.
    target = resolve_target(base_url=base_url, model=model)
    info = probe_concurrency(target.base_url)
    if requires_doctor_confirm(info) and not yes:
        return {
            "ok": False,
            "blocked": True,
            "concurrency": {
                "known_concurrency": info.known_concurrency,
                "single_slot_likely": info.single_slot_likely,
                "source": info.source,
                "detail": info.detail,
            },
            "text": doctor_guard_message(info),
            "requests_executed": 0,
        }

    from minefield.api import plan_checks, run_checks, summarize

    plan = plan_checks(
        base_url=target.base_url,
        mode="doctor",
        max_requests=max_requests,
        model=target.model,
        detect=detect,
    )
    result = run_checks(plan, model=target.model)
    if result.request_budget is not None and result.requests_executed > result.request_budget:
        raise RuntimeError("HARD_BUDGET_VIOLATION")
    summary = summarize(result)
    summary_dict = {
        "clean": getattr(summary, "clean", 0),
        "problem": getattr(summary, "problem", 0),
        "inconclusive": getattr(summary, "inconclusive", 0),
        "findings": [
            {
                "level": getattr(f, "level", ""),
                "code": getattr(f, "code", ""),
                "title": getattr(f, "title", ""),
                "detail": getattr(f, "detail", None),
                "traps": list(getattr(f, "traps", ()) or ()),
            }
            for f in (getattr(summary, "findings", None) or [])
        ],
    }
    text = render_doctor_summary(summary_dict, requests=result.requests_executed)
    if info.known_concurrency == 1:
        text = f"[single-slot confirmed via --yes]\n\n{text}"
    return {
        "ok": True,
        "blocked": False,
        "text": text,
        "requests_executed": result.requests_executed,
        "request_budget": result.request_budget,
        "summary": summary_dict,
        "concurrency": {
            "known_concurrency": info.known_concurrency,
            "single_slot_likely": info.single_slot_likely,
            "source": info.source,
            "detail": info.detail,
        },
    }
