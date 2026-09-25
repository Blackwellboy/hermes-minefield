"""Deterministic incident classification from frozen recorder events.

Compatibility façade: signals live in ``signals.py``, rules in ``rules.py``.
"""

from __future__ import annotations

from .rules import ClassificationResult, RuleContext
from .rules import classify as _classify
from .signals import AnalysisSignals, compute_signals

__all__ = ["AnalysisSignals", "ClassificationResult", "classify", "compute_signals"]


def classify(signals: AnalysisSignals, *, loop_streak_threshold: int | None = None) -> ClassificationResult:
    ctx = (
        RuleContext()
        if loop_streak_threshold is None
        else RuleContext(loop_streak_threshold=loop_streak_threshold)
    )
    return _classify(signals, ctx)
