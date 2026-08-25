"""Deterministic incident classification from frozen recorder events."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from ..recorder.events import (
    API_ERROR,
    TOOL_EXECUTED,
    TOOL_PREPARED,
    TOOL_REQUESTED,
    RecorderEvent,
)
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
    UNKNOWN,
    UI_RENDERING_BUG,
)


@dataclass
class AnalysisSignals:
    prepared_by_tool: dict[str, int]
    executed_by_tool: dict[str, int]
    requested_by_tool: dict[str, int]
    equivalent_executed: dict[str, int]  # tool -> count of fingerprint repeats beyond first
    total_prepared: int
    total_executed: int
    total_api_errors: int
    window_seconds: float
    dominant_tool: Optional[str]


def compute_signals(events: Sequence[RecorderEvent]) -> AnalysisSignals:
    prepared: Counter[str] = Counter()
    executed: Counter[str] = Counter()
    requested: Counter[str] = Counter()
    exec_fps: dict[str, Counter[str]] = defaultdict(Counter)
    api_errors = 0
    ts = [e.ts for e in events]
    window = (max(ts) - min(ts)) if len(ts) >= 2 else 0.0

    for e in events:
        name = e.tool_name or "unknown"
        if e.type == TOOL_PREPARED:
            prepared[name] += 1
        elif e.type == TOOL_REQUESTED:
            requested[name] += 1
        elif e.type == TOOL_EXECUTED:
            executed[name] += 1
            if e.tool_arg_fingerprint:
                exec_fps[name][e.tool_arg_fingerprint] += 1
        elif e.type == API_ERROR:
            api_errors += 1

    equivalent: dict[str, int] = {}
    for tool, fps in exec_fps.items():
        # Sum (count-1) for fingerprints seen more than once
        equivalent[tool] = sum(max(0, c - 1) for c in fps.values())

    dominant = None
    if prepared or executed:
        merged = Counter(prepared) + Counter(executed)
        dominant = merged.most_common(1)[0][0]

    return AnalysisSignals(
        prepared_by_tool=dict(prepared),
        executed_by_tool=dict(executed),
        requested_by_tool=dict(requested),
        equivalent_executed=equivalent,
        total_prepared=sum(prepared.values()),
        total_executed=sum(executed.values()),
        total_api_errors=api_errors,
        window_seconds=window,
        dominant_tool=dominant,
    )


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


def classify(signals: AnalysisSignals) -> ClassificationResult:
    tool = signals.dominant_tool or "tool"
    prep = signals.prepared_by_tool.get(tool, signals.total_prepared)
    exe = signals.executed_by_tool.get(tool, signals.total_executed)
    equiv = signals.equivalent_executed.get(tool, 0)
    window = max(1.0, signals.window_seconds)

    # Fixture A pattern: many prepares, few executes
    if prep >= 10 and exe <= max(2, prep * 0.15):
        return ClassificationResult(
            classification=HERMES_UI_ORCHESTRATION,
            severity=SEVERITY_ANNOYING if prep < 100 else SEVERITY_MEDIUM,
            likely_root_cause=(
                "UI/event renderer repeatedly surfaced the preparation state "
                "while the same operation/model turn was pending."
            ),
            recommended_action=(
                "dedupe repeated preparation-state rendering by request/event identity."
            ),
            serving_failure=False,
            is_engineering_bug=True,
            is_minefield_trap=False,
            confidence="HIGH",
            observed_symptom=(
                f"{prep} `{tool}` preparation events in {window:.0f} seconds."
            ),
        )

    # Fixture B pattern: many executes with equivalent args
    if exe >= 10 and equiv >= max(5, exe * 0.5):
        return ClassificationResult(
            classification=AGENT_TOOL_LOOP,
            severity=SEVERITY_HIGH,
            likely_root_cause=(
                "agent tool loop repeatedly selected materially identical tool requests."
            ),
            recommended_action=(
                "add equivalent-tool-call suppression / loop breaker."
            ),
            serving_failure=False,
            is_engineering_bug=True,
            is_minefield_trap=False,
            confidence="HIGH",
            observed_symptom=(
                f"{prep} `{tool}` preparations; {exe} executions "
                f"({equiv} equivalent-argument repeats)."
            ),
        )

    if signals.total_api_errors >= 3:
        return ClassificationResult(
            classification=MODEL_SERVER_BUG,
            severity=SEVERITY_MEDIUM,
            likely_root_cause="burst of API request errors in the frozen window.",
            recommended_action="inspect server logs; run /minefield check on the endpoint.",
            serving_failure=True,
            is_engineering_bug=False,
            is_minefield_trap=False,
            confidence="MEDIUM",
            observed_symptom=f"{signals.total_api_errors} API errors in window.",
        )

    if prep == 0 and exe == 0 and signals.total_api_errors == 0:
        return ClassificationResult(
            classification=UNKNOWN,
            severity=SEVERITY_LOW,
            likely_root_cause="no strong tool/API anomaly in the frozen window.",
            recommended_action="widen the window (/minefield wtf 10m) or reproduce once.",
            serving_failure=False,
            is_engineering_bug=False,
            is_minefield_trap=False,
            confidence="LOW",
            observed_symptom="quiet window — nothing obviously weird in recorder metadata.",
        )

    if prep > 0 and exe == prep:
        return ClassificationResult(
            classification=EXPECTED_BEHAVIOUR,
            severity=SEVERITY_LOW,
            likely_root_cause="preparation and execution counts match.",
            recommended_action="no action unless user still sees wrong UX.",
            serving_failure=False,
            is_engineering_bug=False,
            is_minefield_trap=False,
            confidence="MEDIUM",
            observed_symptom=f"{prep} prepare / {exe} execute for `{tool}` — aligned.",
        )

    return ClassificationResult(
        classification=UI_RENDERING_BUG if prep > exe else UNKNOWN,
        severity=SEVERITY_LOW,
        likely_root_cause="mild prepare/execute mismatch; not a clear loop.",
        recommended_action="capture another sample or include optional arg details with consent.",
        serving_failure=False,
        is_engineering_bug=prep > exe * 2,
        is_minefield_trap=False,
        confidence="LOW",
        observed_symptom=f"{prep} prepare vs {exe} execute for `{tool}`.",
    )
