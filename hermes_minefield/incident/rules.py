"""Classification rules: one pure function each, evaluated in priority order.

``classify`` returns the first rule that fires. Keep every rule small, give it
a fixture under ``fixtures/rules/``, and document it in docs/CLASSIFICATION.md.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .signals import AnalysisSignals, percentile
from .tool_classes import is_idempotent
from .types import (
    AGENT_TOOL_LOOP,
    CONFIGURATION_ERROR,
    EXPECTED_BEHAVIOUR,
    HERMES_UI_ORCHESTRATION,
    MODEL_SERVER_BUG,
    PERFORMANCE_CONTENTION,
    SEVERITY_ANNOYING,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    TOOL_BUG,
    UI_RENDERING_BUG,
    UNKNOWN,
)

DEFAULT_LOOP_STREAK = 5
SLOW_P95_MS = 60_000.0
SLOW_TTFT_P95_MS = 20_000.0


@dataclass
class ClassificationResult:
    classification: str
    severity: str
    likely_root_cause: str
    recommended_action: str
    serving_failure: bool
    is_engineering_bug: bool
    is_minefield_trap: bool
    confidence: str
    observed_symptom: str
    rule: str = ""


@dataclass(frozen=True)
class RuleContext:
    loop_streak_threshold: int = DEFAULT_LOOP_STREAK


Rule = Callable[[AnalysisSignals, RuleContext], "ClassificationResult | None"]


def _result(rule: str, **kw) -> ClassificationResult:
    kw.setdefault("is_minefield_trap", False)
    return ClassificationResult(rule=rule, **kw)


def rule_auth_failure(s: AnalysisSignals, ctx: RuleContext) -> ClassificationResult | None:
    n = s.api_status_counts.get("401", 0) + s.api_status_counts.get("403", 0)
    if n < 1:
        return None
    return _result(
        "auth_failure",
        classification=CONFIGURATION_ERROR,
        severity=SEVERITY_HIGH,
        likely_root_cause="the model endpoint rejected Hermes's credentials (401/403).",
        recommended_action="check the provider API key / auth (`hermes auth`), then retry.",
        serving_failure=False,
        is_engineering_bug=False,
        confidence="HIGH",
        observed_symptom=f"{n} API request(s) failed with 401/403.",
    )


def rule_rate_limited(s: AnalysisSignals, ctx: RuleContext) -> ClassificationResult | None:
    n = s.api_status_counts.get("429", 0)
    if n < 3:
        return None
    return _result(
        "rate_limited",
        classification=PERFORMANCE_CONTENTION,
        severity=SEVERITY_MEDIUM,
        likely_root_cause="the provider is rate-limiting requests (HTTP 429).",
        recommended_action="slow down, raise the provider quota, or use another endpoint.",
        serving_failure=True,
        is_engineering_bug=False,
        confidence="HIGH",
        observed_symptom=f"{n} API requests rejected with 429.",
    )


def rule_server_errors(s: AnalysisSignals, ctx: RuleContext) -> ClassificationResult | None:
    n = s.api_status_counts.get("5xx", 0) + s.api_status_counts.get("none", 0)
    if n < 3:
        return None
    return _result(
        "server_errors",
        classification=MODEL_SERVER_BUG,
        severity=SEVERITY_MEDIUM,
        likely_root_cause="burst of server-side / connection errors from the model endpoint.",
        recommended_action="inspect server logs; run /minefield check on the endpoint.",
        serving_failure=True,
        is_engineering_bug=False,
        confidence="MEDIUM",
        observed_symptom=f"{n} API errors (5xx or no response) in window.",
    )


def rule_tool_hang(s: AnalysisSignals, ctx: RuleContext) -> ClassificationResult | None:
    if not s.hung_by_tool:
        return None
    tool, n = max(s.hung_by_tool.items(), key=lambda kv: kv[1])
    return _result(
        "tool_hang",
        classification=TOOL_BUG,
        severity=SEVERITY_MEDIUM,
        likely_root_cause=f"tool appears hung: `{tool}` was dispatched but never finished.",
        recommended_action="check the tool process (terminal/browser/MCP server) and its timeout.",
        serving_failure=False,
        is_engineering_bug=True,
        confidence="MEDIUM",
        observed_symptom=f"{n} `{tool}` call(s) started >2 minutes ago with no result.",
    )


def rule_tool_loop(s: AnalysisSignals, ctx: RuleContext) -> ClassificationResult | None:
    if s.longest_streak < ctx.loop_streak_threshold or not s.streak_tool:
        return None
    tool = s.streak_tool
    idempotent = is_idempotent(tool)
    return _result(
        "tool_loop",
        classification=AGENT_TOOL_LOOP,
        severity=SEVERITY_HIGH,
        likely_root_cause=(
            f"agent repeated `{tool}` {s.longest_streak} times in a row with identical arguments "
            "and identical results — no progress."
        ),
        recommended_action="add equivalent-tool-call suppression / loop breaker (Hermes tool_loop_guardrails).",
        serving_failure=False,
        is_engineering_bug=True,
        confidence="HIGH" if idempotent else "MEDIUM",
        observed_symptom=f"{s.longest_streak} consecutive identical `{tool}` calls (same args, same result).",
    )


def rule_failure_storm(s: AnalysisSignals, ctx: RuleContext) -> ClassificationResult | None:
    if not s.failed_by_tool:
        return None
    tool, n_failed = max(s.failed_by_tool.items(), key=lambda kv: kv[1])
    n_exec = max(n_failed, s.executed_by_tool.get(tool, 0))
    if n_failed < 5 or n_failed < 0.5 * n_exec:
        return None
    return _result(
        "failure_storm",
        classification=TOOL_BUG,
        severity=SEVERITY_MEDIUM,
        likely_root_cause=f"`{tool}` failed {n_failed} of {n_exec} executions in the window.",
        recommended_action="inspect the tool's errors (hermes logs); check its config/permissions.",
        serving_failure=False,
        is_engineering_bug=True,
        confidence="MEDIUM",
        observed_symptom=f"{n_failed}/{n_exec} `{tool}` executions failed.",
    )


def rule_not_dispatched(s: AnalysisSignals, ctx: RuleContext) -> ClassificationResult | None:
    prep, req, exe = s.total_prepared, s.total_requested, s.total_executed
    dispatched = max(req, exe)
    storm = prep >= 10 and dispatched <= max(2, prep * 0.15)
    by_id = s.undispatched >= 5
    if not (storm or by_id):
        return None
    missing = s.undispatched if by_id else prep - dispatched
    tool = s.dominant_tool or "tool"
    return _result(
        "not_dispatched",
        classification=HERMES_UI_ORCHESTRATION,
        severity=SEVERITY_ANNOYING if prep < 100 else SEVERITY_MEDIUM,
        likely_root_cause=(
            "model-emitted tool calls were not dispatched: blocked by a guardrail/approval, "
            "dropped, or an orchestration/rendering bug repeating the same pending call."
        ),
        recommended_action="dedupe repeated tool-call preparation by request/call identity; check approvals.",
        serving_failure=False,
        is_engineering_bug=True,
        confidence="HIGH" if storm else "MEDIUM",
        observed_symptom=f"{prep} `{tool}` tool calls prepared, {dispatched} dispatched ({missing} never ran).",
    )


def rule_slow_model(s: AnalysisSignals, ctx: RuleContext) -> ClassificationResult | None:
    p95 = percentile(s.api_latency_ms, 0.95) if len(s.api_latency_ms) >= 3 else None
    t95 = percentile(s.api_ttft_ms, 0.95) if len(s.api_ttft_ms) >= 3 else None
    slow = (p95 is not None and p95 > SLOW_P95_MS) or (t95 is not None and t95 > SLOW_TTFT_P95_MS)
    if not slow:
        return None
    parts = []
    if p95 is not None:
        parts.append(f"p95 latency {p95 / 1000:.0f}s")
    if t95 is not None:
        parts.append(f"p95 TTFT {t95 / 1000:.0f}s")
    return _result(
        "slow_model",
        classification=PERFORMANCE_CONTENTION,
        severity=SEVERITY_LOW,
        likely_root_cause="model responses are very slow (queueing, contention or an overloaded server).",
        recommended_action="check server load/slots; run /minefield check.",
        serving_failure=True,
        is_engineering_bug=False,
        confidence="MEDIUM",
        observed_symptom=", ".join(parts) + f" over {len(s.api_latency_ms)} responses.",
    )


def rule_quiet(s: AnalysisSignals, ctx: RuleContext) -> ClassificationResult | None:
    if s.total_prepared or s.total_requested or s.total_executed or s.total_api_errors or s.api_responses:
        return None
    return _result(
        "quiet",
        classification=UNKNOWN,
        severity=SEVERITY_LOW,
        likely_root_cause="no tool/API activity in the frozen window.",
        recommended_action="widen the window (/minefield wtf 10m) or reproduce once.",
        serving_failure=False,
        is_engineering_bug=False,
        confidence="LOW",
        observed_symptom="quiet window — nothing obviously weird in recorder metadata.",
    )


def rule_aligned(s: AnalysisSignals, ctx: RuleContext) -> ClassificationResult | None:
    tool = s.dominant_tool or "tool"
    if s.total_requested:
        # Every dispatched call finished (or is still in flight, not hung).
        if s.total_executed + s.in_flight < s.total_requested:
            return None
        symptom = f"{s.total_requested} dispatched / {s.total_executed} executed — aligned."
    elif s.total_prepared:
        # Legacy windows (<=0.1.x fixtures): prepared ≈ executed.
        if s.total_executed != s.total_prepared:
            return None
        symptom = f"{s.total_prepared} prepare / {s.total_executed} execute for `{tool}` — aligned."
    elif s.total_executed:
        # Executions without dispatch records (older recorder data, or the window
        # started mid-call): no failures, loops or hangs were found above.
        symptom = f"{s.total_executed} execution(s), no dispatch records — no anomalies."
    else:
        symptom = f"{s.api_responses} model response(s), no tool calls, no errors."
    return _result(
        "aligned",
        classification=EXPECTED_BEHAVIOUR,
        severity=SEVERITY_LOW,
        likely_root_cause="tool dispatch and execution counts match; no errors or loops.",
        recommended_action="no action unless you still see wrong UX.",
        serving_failure=False,
        is_engineering_bug=False,
        confidence="MEDIUM",
        observed_symptom=symptom,
    )


def rule_fallback(s: AnalysisSignals, ctx: RuleContext) -> ClassificationResult:
    tool = s.dominant_tool or "tool"
    dispatched = max(s.total_requested, s.total_prepared)
    return _result(
        "fallback",
        classification=UI_RENDERING_BUG if dispatched > s.total_executed else UNKNOWN,
        severity=SEVERITY_LOW,
        likely_root_cause="mild dispatch/execute mismatch; not a clear loop or failure pattern.",
        recommended_action="capture another sample (/minefield wtf 10m).",
        serving_failure=False,
        is_engineering_bug=dispatched > s.total_executed * 2,
        confidence="LOW",
        observed_symptom=f"{dispatched} dispatched vs {s.total_executed} executed for `{tool}`.",
    )


RULES: tuple[Rule, ...] = (
    rule_auth_failure,
    rule_rate_limited,
    rule_server_errors,
    rule_tool_hang,
    rule_tool_loop,
    rule_failure_storm,
    rule_not_dispatched,
    rule_slow_model,
    rule_quiet,
    rule_aligned,
)


def classify(signals: AnalysisSignals, ctx: RuleContext | None = None) -> ClassificationResult:
    ctx = ctx or RuleContext()
    for rule in RULES:
        result = rule(signals, ctx)
        if result is not None:
            return result
    return rule_fallback(signals, ctx)
