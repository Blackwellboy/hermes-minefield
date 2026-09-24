"""Classification rules, one fixture each (plan T3.2 + T3.4). See fixtures/rules/."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from hermes_minefield.incident import rules
from hermes_minefield.incident.classify import classify, compute_signals
from hermes_minefield.recorder.events import RecorderEvent

RULE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "rules"
FIXTURES = sorted(p.stem for p in RULE_DIR.glob("*.json"))


def _fmt(value, i):
    if isinstance(value, str):
        return value.replace("{i}", str(i))
    if isinstance(value, dict):
        return {k: _fmt(v, i) for k, v in value.items()}
    return value


def build_events(spec: list[dict], now: float) -> list[RecorderEvent]:
    """Fixture DSL: {"repeat": n, ...event} or {"repeat": n, "each": [events]}; "{i}" is the
    repetition index; "age_s" = seconds before now (default: sequential, 1s apart)."""
    flat: list[dict] = []
    for item in spec:
        n = item.get("repeat", 1)
        body = {k: v for k, v in item.items() if k != "repeat"}
        for i in range(n):
            group = body["each"] if "each" in body else [body]
            flat.extend(_fmt(ev, i) for ev in group)
    events = []
    for idx, row in enumerate(flat):
        row = dict(row)
        age = row.pop("age_s", len(flat) - idx)
        events.append(RecorderEvent(ts=now - age, **row))
    return events


def load(name: str):
    doc = json.loads((RULE_DIR / f"{name}.json").read_text())
    return doc, build_events(doc["events"], time.time())


@pytest.mark.parametrize("name", FIXTURES)
def test_rule_fixture(name):
    doc, events = load(name)
    result = classify(compute_signals(events))
    got = {k: getattr(result, k) for k in doc["expected"]}
    assert got == doc["expected"], f"{name}: {doc['about']}"


def test_every_rule_has_a_fixture():
    covered = set()
    for name in FIXTURES:
        covered.add(json.loads((RULE_DIR / f"{name}.json").read_text())["expected"].get("rule"))
    names = {r.__name__.removeprefix("rule_") for r in rules.RULES}
    assert names <= covered, f"rules without a fixture: {sorted(names - covered)}"


def test_loop_threshold_is_configurable():
    _, events = load("tool_loop_idempotent")  # streak of 6
    assert classify(compute_signals(events), loop_streak_threshold=7).rule != "tool_loop"
    assert classify(compute_signals(events), loop_streak_threshold=6).rule == "tool_loop"


def test_streak_signal_value():
    _, events = load("tool_loop_idempotent")
    s = compute_signals(events)
    assert (s.longest_streak, s.streak_tool) == (6, "read_file")
