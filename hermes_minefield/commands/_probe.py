"""Shared handling of a Minefield probe run for check (Lite) and doctor.

The one job of this module: never let "could not test" look like "clean".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .. import verdict as V
from ..privacy import redact_text
from ..render import counts_from_findings


@dataclass
class ProbeOutcome:
    ok: bool
    verdict: str
    reason: str
    summary: dict[str, Any] | None  # None when nothing valid ran (never cached)
    requests_executed: int
    request_budget: int | None
    error: str | None = None


def scrub(text: Any, secrets: tuple[str, ...] = ()) -> str:
    """Exact-value scrub of known secrets, then generic redaction."""
    out = str(text or "")
    for secret in secrets:
        if secret and len(secret) >= 8:
            out = out.replace(secret, "[REDACTED]")
    return redact_text(out)


def _finding_dict(f: Any, secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    def get(name: str, default: Any = "") -> Any:
        if isinstance(f, dict):
            return f.get(name, default)
        return getattr(f, name, default)

    return {
        "level": scrub(get("level"), secrets),
        "code": scrub(get("code"), secrets),
        "title": scrub(get("title"), secrets),
        "detail": scrub(get("detail"), secrets),
        "traps": [scrub(t, secrets) for t in (get("traps", ()) or ())],
    }


def evaluate_run(result: Any, summary_fn, *, secrets: tuple[str, ...] = ()) -> ProbeOutcome:
    """Turn a minefield ``RunResult`` into a verdict + cacheable summary (or not).

    ``secrets`` (e.g. the API key) are scrubbed from everything we keep or print.
    """
    executed = int(getattr(result, "requests_executed", 0) or 0)
    budget = getattr(result, "request_budget", None)

    if getattr(result, "budget_exceeded", False) or (budget is not None and executed > budget):
        return ProbeOutcome(
            ok=False,
            verdict=V.UNKNOWN,
            reason=f"HARD_BUDGET_VIOLATION: executed {executed} > budget {budget}; results discarded",
            summary=None,
            requests_executed=executed,
            request_budget=budget,
            error="budget_exceeded",
        )

    error = getattr(result, "error", None)
    if getattr(result, "reachable", True) is False or error:
        err = scrub(error or "target_unreachable", secrets)
        return ProbeOutcome(
            ok=False,
            verdict=V.UNKNOWN,
            reason=f"endpoint could not be tested ({err}); nothing cached",
            summary=None,
            requests_executed=executed,
            request_budget=budget,
            error=err,
        )

    summary = summary_fn(result)
    findings = [_finding_dict(f, secrets) for f in (getattr(summary, "findings", None) or [])]
    clean = int(getattr(summary, "clean_count", 0) or 0)
    problem = int(getattr(summary, "problem_count", 0) or 0)
    inconclusive = int(getattr(summary, "inconclusive_count", 0) or 0)
    derived = counts_from_findings(findings)
    if (clean, problem, inconclusive) == (0, 0, 0) and derived != (0, 0, 0):
        clean, problem, inconclusive = derived

    if executed == 0 and not findings:
        return ProbeOutcome(
            ok=False,
            verdict=V.UNKNOWN,
            reason="no probes executed (endpoint unreachable, or no applicable probes for this stack); nothing cached",
            summary=None,
            requests_executed=0,
            request_budget=budget,
            error="no_probes_executed",
        )

    verdict = V.from_counts(clean=clean, problem=problem, inconclusive=inconclusive)
    reason = {
        V.PASS: "probes ran and every finding is clean",
        V.FAIL: f"{problem} problem finding(s)",
        V.UNKNOWN: f"{inconclusive} inconclusive finding(s), {clean} clean — not enough evidence for PASS",
    }[verdict]
    summary_dict = {
        "clean": clean,
        "problem": problem,
        "inconclusive": inconclusive,
        "clean_count": clean,
        "problem_count": problem,
        "inconclusive_count": inconclusive,
        "skipped": int(getattr(summary, "skipped_probe_count", 0) or 0),
        "findings": findings,
        "requests_made": executed,
        "verdict": verdict,
    }
    return ProbeOutcome(
        ok=True,
        verdict=verdict,
        reason=reason,
        summary=summary_dict,
        requests_executed=executed,
        request_budget=budget,
    )
