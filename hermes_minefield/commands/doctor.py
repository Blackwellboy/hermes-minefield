"""Full Minefield Doctor — explicit only, with single-slot guard."""

from __future__ import annotations

from typing import Any

from .. import verdict as V
from ..concurrency import doctor_guard_message, probe_concurrency, requires_doctor_confirm
from ..render import render_doctor_summary
from ..target import resolve_target
from ._probe import evaluate_run
from .check import url_shape


def run_doctor(
    *,
    base_url: str | None = None,
    model: str | None = None,
    yes: bool = False,
    max_requests: int | None = None,
    detect: bool = True,
) -> dict[str, Any]:
    try:
        target = resolve_target(base_url=base_url, model=model)
    except ValueError as e:
        reason = f"target could not be resolved: {e}"
        return {
            "ok": False,
            "blocked": False,
            "verdict": V.UNKNOWN,
            "text": f"Minefield Doctor\n\n{V.line(V.UNKNOWN, reason)}",
            "requests_executed": 0,
        }

    # Concurrency guard BEFORE importing Minefield, so a blocked single-slot run
    # never depends on minefield being importable and never issues Doctor requests.
    info = probe_concurrency(target.base_url)
    concurrency = {
        "known_concurrency": info.known_concurrency,
        "single_slot_likely": info.single_slot_likely,
        "source": info.source,
        "detail": info.detail,
    }
    if requires_doctor_confirm(info) and not yes:
        return {
            "ok": False,
            "blocked": True,
            "verdict": V.UNKNOWN,
            "concurrency": concurrency,
            "text": f"{doctor_guard_message(info)}\n\n{V.line(V.UNKNOWN, 'not run — needs --yes')}",
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
    outcome = evaluate_run(result, summarize)
    prefix = "[single-slot confirmed via --yes]\n\n" if info.known_concurrency == 1 else ""

    if outcome.summary is None:
        text = (
            f"Minefield Doctor\nendpoint: {url_shape(target.base_url)}\n\n"
            f"{outcome.requests_executed} requests\n\n{V.line(outcome.verdict, outcome.reason)}"
        )
        return {
            "ok": False,
            "blocked": False,
            "verdict": outcome.verdict,
            "text": prefix + text,
            "requests_executed": outcome.requests_executed,
            "request_budget": outcome.request_budget,
            "error": outcome.error,
            "concurrency": concurrency,
        }

    text = render_doctor_summary(outcome.summary, requests=outcome.requests_executed)
    return {
        "ok": True,
        "blocked": False,
        "verdict": outcome.verdict,
        "text": f"{prefix}{text}\n\n{V.line(outcome.verdict, outcome.reason)}",
        "requests_executed": outcome.requests_executed,
        "request_budget": outcome.request_budget,
        "summary": outcome.summary,
        "concurrency": concurrency,
    }
