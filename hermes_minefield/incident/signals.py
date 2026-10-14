"""Pure signal extraction from a frozen recorder window.

Tool lifecycle (plan T3.1):
- ``tool.prepared``  — the model emitted a tool call (from ``post_api_request``);
- ``tool.requested`` — Hermes dispatched it (``pre_tool_call``);
- ``tool.executed``  — it finished (``post_tool_call``), plus completed/failed.

Events persisted by <=0.1.x recorded ``tool.prepared`` from ``pre_tool_call``
(``extra.phase == "pre_tool_call"``) alongside ``tool.requested``; those are
not counted as "prepared" so old windows don't look like undispatched calls.
"""

from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from ..recorder.events import (
    API_ERROR,
    API_RESPONSE,
    TOOL_EXECUTED,
    TOOL_FAILED,
    TOOL_PREPARED,
    TOOL_REQUESTED,
    RecorderEvent,
)
from .tool_classes import is_poller

HANG_SECONDS = 120.0


@dataclass
class AnalysisSignals:
    prepared_by_tool: dict[str, int]
    executed_by_tool: dict[str, int]
    requested_by_tool: dict[str, int]
    equivalent_executed: dict[str, int]  # tool -> repeats beyond first of identical (args, result)
    total_prepared: int
    total_executed: int
    total_api_errors: int
    window_seconds: float
    dominant_tool: str | None
    failed_by_tool: dict[str, int] = field(default_factory=dict)
    total_failed: int = 0
    total_requested: int = 0
    # Longest consecutive run of identical (tool, args, result) executions in one session.
    longest_streak: int = 0
    streak_tool: str | None = None
    # Model-emitted tool calls Hermes never dispatched (matched by tool_call id when known).
    undispatched: int = 0
    # Dispatched but never finished, older than HANG_SECONDS at freeze time.
    hung_by_tool: dict[str, int] = field(default_factory=dict)
    in_flight: int = 0
    api_status_counts: dict[str, int] = field(default_factory=dict)  # "401", "5xx", "none", …
    api_latency_ms: list[float] = field(default_factory=list)
    api_ttft_ms: list[float] = field(default_factory=list)
    api_responses: int = 0
    guard_blocks: int | None = None  # None = not observable (older Hermes)
    interrupted_turns: int = 0
    event_count: int = 0


def _call_id(e: RecorderEvent) -> str | None:
    cid = e.extra.get("tool_call_id_hash") if e.extra else None
    return cid if isinstance(cid, str) and cid else None


def _is_legacy_pre_prepare(e: RecorderEvent) -> bool:
    return bool(e.extra) and e.extra.get("phase") == "pre_tool_call"


def _status_bucket(status: int | None) -> str:
    if status is None:
        return "none"
    if status in (401, 403, 429):
        return str(status)
    if 500 <= status <= 599:
        return "5xx"
    return "other"


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[idx]


def compute_signals(events: Sequence[RecorderEvent], *, now: float | None = None) -> AnalysisSignals:
    now = time.time() if now is None else now
    prepared: Counter[str] = Counter()
    requested: Counter[str] = Counter()
    executed: Counter[str] = Counter()
    failed: Counter[str] = Counter()
    exec_keys: dict[str, Counter[str]] = defaultdict(Counter)
    prepared_ids: set[str] = set()
    requested_ids: dict[str, tuple[str, float]] = {}
    executed_ids: set[str] = set()
    status_counts: Counter[str] = Counter()
    latency: list[float] = []
    ttft: list[float] = []
    api_responses = 0
    guard_blocks = 0
    guard_observable = False
    interrupted = 0
    api_errors = 0

    # Streak state per session: (key, run length)
    streak_state: dict[str | None, tuple[str | None, int]] = {}
    longest, streak_tool = 0, None

    ordered = sorted(events, key=lambda e: e.ts)
    for e in ordered:
        name = e.tool_name or "unknown"
        if e.type == TOOL_PREPARED:
            if _is_legacy_pre_prepare(e):
                continue
            prepared[name] += 1
            if cid := _call_id(e):
                prepared_ids.add(cid)
        elif e.type == TOOL_REQUESTED:
            requested[name] += 1
            if cid := _call_id(e):
                requested_ids[cid] = (name, e.ts)
        elif e.type == TOOL_EXECUTED:
            executed[name] += 1
            if cid := _call_id(e):
                executed_ids.add(cid)
            if e.extra and "guardrail_refusal" in e.extra:
                guard_observable = True
                guard_blocks += 1 if e.extra.get("guardrail_refusal") else 0
            if e.tool_arg_fingerprint:
                key = e.tool_arg_fingerprint
                if e.result_fingerprint:
                    key = f"{key}|{e.result_fingerprint}"
                exec_keys[name][key] += 1
                full_key = f"{name}|{key}"
                prev_key, run = streak_state.get(e.session_id_hash, (None, 0))
                run = run + 1 if prev_key == full_key else 1
                streak_state[e.session_id_hash] = (full_key, run)
                if run > longest and not is_poller(name):
                    longest, streak_tool = run, name
            else:
                streak_state[e.session_id_hash] = (None, 0)
        elif e.type == TOOL_FAILED:
            failed[name] += 1
        elif e.type == API_ERROR:
            api_errors += 1
            status_counts[_status_bucket(e.http_status)] += 1
        elif e.type == API_RESPONSE:
            api_responses += 1
            if e.wall_ms is not None:
                latency.append(e.wall_ms)
            if e.ttft_ms is not None:
                ttft.append(e.ttft_ms)
        if e.extra and e.extra.get("interrupted") is True:
            interrupted += 1

    equivalent = {tool: sum(max(0, c - 1) for c in keys.values()) for tool, keys in exec_keys.items()}

    undispatched = len(prepared_ids - set(requested_ids)) if prepared_ids else 0
    hung: Counter[str] = Counter()
    in_flight = 0
    for cid, (name, ts) in requested_ids.items():
        if cid in executed_ids:
            continue
        if now - ts > HANG_SECONDS:
            hung[name] += 1
        else:
            in_flight += 1

    ts = [e.ts for e in events]
    window = (max(ts) - min(ts)) if len(ts) >= 2 else 0.0
    activity = prepared + requested + executed
    dominant = activity.most_common(1)[0][0] if activity else None

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
        failed_by_tool=dict(failed),
        total_failed=sum(failed.values()),
        total_requested=sum(requested.values()),
        longest_streak=longest,
        streak_tool=streak_tool,
        undispatched=undispatched,
        hung_by_tool=dict(hung),
        in_flight=in_flight,
        api_status_counts=dict(status_counts),
        api_latency_ms=latency,
        api_ttft_ms=ttft,
        api_responses=api_responses,
        guard_blocks=guard_blocks if guard_observable else None,
        interrupted_turns=interrupted,
        event_count=len(events),
    )
