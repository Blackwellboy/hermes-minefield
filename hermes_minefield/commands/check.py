"""Minefield Lite — /minefield check (budgeted plan/run/summarize)."""

from __future__ import annotations

import time
from typing import Any, Optional

from ..cache import CacheEntry, get_entry, put_entry
from ..config import DEFAULT_LITE_MAX_REQUESTS, load_plugin_config
from ..fingerprint import fingerprint_for_hermes_target
from ..render import counts_from_findings, render_lite_summary
from ..target import resolve_target


def run_check(
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    max_requests: Optional[int] = None,
    detect: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Execute Lite via Minefield library API (no subprocess, no stdout parse)."""
    from minefield.api import plan_checks, run_checks, summarize

    cfg = load_plugin_config()
    if max_requests is not None:
        budget = int(max_requests)
    else:
        budget = min(int(cfg.lite_max_requests), DEFAULT_LITE_MAX_REQUESTS)
    if budget < 0:
        raise ValueError("max_requests must be >= 0")

    target = resolve_target(base_url=base_url, model=model)
    # Same key as status — do not omit reasoning_mode or cache lookups diverge.
    fp = fingerprint_for_hermes_target(model=target.model, base_url=target.base_url)
    cached = get_entry(fp.key)
    if cached and not force:
        return {
            "ok": True,
            "cached": True,
            "fingerprint": fp.short(),
            "text": render_lite_summary(
                cached.summary,
                requests=cached.requests_executed,
                fingerprint_short=fp.short(),
            )
            + "\n\n(cached — pass --force to re-run)",
            "requests_executed": cached.requests_executed,
            "summary": cached.summary,
        }

    plan = plan_checks(
        base_url=target.base_url,
        mode="lite",
        max_requests=int(budget),
        model=target.model,
        detect=detect,
    )
    assert plan.expected_requests <= int(budget)
    result = run_checks(plan, model=target.model)
    if result.request_budget is not None:
        assert result.requests_executed <= result.request_budget
    summary = summarize(result)
    findings = [
        {
            "level": getattr(f, "level", None) or (f.get("level") if isinstance(f, dict) else ""),
            "code": getattr(f, "code", None) or (f.get("code") if isinstance(f, dict) else ""),
            "title": getattr(f, "title", None) or (f.get("title") if isinstance(f, dict) else ""),
            "detail": getattr(f, "detail", None) or (f.get("detail") if isinstance(f, dict) else ""),
            "traps": list(getattr(f, "traps", ()) or (f.get("traps") if isinstance(f, dict) else [])),
        }
        for f in (getattr(summary, "findings", None) or [])
    ]
    # Minefield Summary uses clean_count/problem_count/… (not clean/problem).
    clean = int(getattr(summary, "clean_count", None) or 0)
    problem = int(getattr(summary, "problem_count", None) or 0)
    inconclusive = int(getattr(summary, "inconclusive_count", None) or 0)
    derived = counts_from_findings(findings)
    if (clean, problem, inconclusive) == (0, 0, 0) and derived != (0, 0, 0):
        clean, problem, inconclusive = derived
    summary_dict = {
        "clean": clean,
        "problem": problem,
        "inconclusive": inconclusive,
        "clean_count": clean,
        "problem_count": problem,
        "inconclusive_count": inconclusive,
        "skipped": int(getattr(summary, "skipped_probe_count", None) or 0),
        "findings": findings,
        "requests_made": result.requests_executed,
    }
    put_entry(
        CacheEntry(
            fingerprint=fp.key,
            checked_at=time.time(),
            mode="lite",
            summary=summary_dict,
            requests_executed=result.requests_executed,
            clean=summary_dict["clean"],
            problem=summary_dict["problem"],
            inconclusive=summary_dict["inconclusive"],
        )
    )
    text = render_lite_summary(
        summary_dict, requests=result.requests_executed, fingerprint_short=fp.short()
    )
    return {
        "ok": True,
        "cached": False,
        "fingerprint": fp.short(),
        "text": text,
        "requests_executed": result.requests_executed,
        "request_budget": result.request_budget,
        "summary": summary_dict,
        "plan_selected": list(plan.selected_ids),
    }
