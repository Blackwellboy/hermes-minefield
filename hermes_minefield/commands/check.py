"""Minefield Lite — /minefield check (budgeted plan/run/summarize)."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlsplit

from .. import verdict as V
from ..cache import CacheEntry, get_entry, put_entry
from ..config import DEFAULT_LITE_MAX_REQUESTS, load_plugin_config
from ..fingerprint import fingerprint_for_hermes_target
from ..render import extract_summary_counts, render_lite_summary
from ..target import resolve_target
from ._probe import evaluate_run


def url_shape(base_url: str) -> str:
    """Printable endpoint without host/credentials (slash output may land in a group chat)."""
    try:
        parts = urlsplit(base_url)
        return f"{parts.scheme}://[host]{parts.path}"
    except Exception:
        return "[endpoint]"


def cached_verdict(summary: dict[str, Any]) -> str:
    stored = summary.get("verdict") if isinstance(summary, dict) else None
    if stored in (V.PASS, V.FAIL, V.UNKNOWN):
        return stored
    _, clean, problem, inconclusive = extract_summary_counts(summary)
    return V.from_counts(clean=clean, problem=problem, inconclusive=inconclusive)


def unknown_result(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "verdict": V.UNKNOWN,
        "text": f"Minefield Lite\n\n{V.line(V.UNKNOWN, reason)}",
        "requests_executed": 0,
        **extra,
    }


def run_check(
    *,
    base_url: str | None = None,
    model: str | None = None,
    max_requests: int | None = None,
    detect: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Execute Lite via the Minefield library API (no subprocess, no stdout parsing)."""
    cfg = load_plugin_config()
    if max_requests is not None:
        budget = int(max_requests)
    else:
        budget = min(int(cfg.lite_max_requests), DEFAULT_LITE_MAX_REQUESTS)
    if budget < 0:
        raise ValueError("max_requests must be >= 0")

    try:
        target = resolve_target(base_url=base_url, model=model)
    except ValueError as e:
        return unknown_result(f"target could not be resolved: {e}")

    # Same key as status — do not omit reasoning_mode or cache lookups diverge.
    fp = fingerprint_for_hermes_target(model=target.model, base_url=target.base_url)
    cached = get_entry(fp.key, ttl_days=cfg.fingerprint_cache_ttl_days)
    if cached and not force:
        verdict = cached_verdict(cached.summary)
        age_min = (time.time() - cached.checked_at) / 60
        text = render_lite_summary(
            cached.summary, requests=cached.requests_executed, fingerprint_short=fp.short()
        )
        return {
            "ok": True,
            "cached": True,
            "verdict": verdict,
            "fingerprint": fp.short(),
            "text": f"{text}\n\n{V.line(verdict, f'cached {age_min:.0f}m ago — pass --force to re-run')}",
            "requests_executed": cached.requests_executed,
            "summary": cached.summary,
        }

    from minefield.api import plan_checks, run_checks, summarize

    plan = plan_checks(
        base_url=target.base_url,
        mode="lite",
        max_requests=budget,
        model=target.model,
        detect=detect,
        api_key=target.api_key,
    )
    if plan.expected_requests > budget:
        raise RuntimeError(f"HARD_BUDGET_VIOLATION: plan expects {plan.expected_requests} > budget {budget}")
    result = run_checks(plan, model=target.model, api_key=target.api_key)
    outcome = evaluate_run(result, summarize, secrets=(target.api_key or "",))

    if outcome.summary is None:
        return {
            "ok": False,
            "cached": False,
            "verdict": outcome.verdict,
            "fingerprint": fp.short(),
            "text": (
                f"Minefield Lite — fingerprint {fp.short()}\n"
                f"endpoint: {url_shape(target.base_url)}\n\n"
                f"{outcome.requests_executed} requests\n\n"
                f"{V.line(outcome.verdict, outcome.reason)}"
            ),
            "requests_executed": outcome.requests_executed,
            "request_budget": outcome.request_budget,
            "error": outcome.error,
        }

    summary_dict = outcome.summary
    put_entry(
        CacheEntry(
            fingerprint=fp.key,
            checked_at=time.time(),
            mode="lite",
            summary=summary_dict,
            requests_executed=outcome.requests_executed,
            clean=summary_dict["clean"],
            problem=summary_dict["problem"],
            inconclusive=summary_dict["inconclusive"],
        )
    )
    text = render_lite_summary(summary_dict, requests=outcome.requests_executed, fingerprint_short=fp.short())
    return {
        "ok": True,
        "cached": False,
        "verdict": outcome.verdict,
        "fingerprint": fp.short(),
        "text": f"{text}\n\n{V.line(outcome.verdict, outcome.reason)}",
        "requests_executed": outcome.requests_executed,
        "request_budget": outcome.request_budget,
        "summary": summary_dict,
        "plan_selected": list(plan.selected_ids),
    }
