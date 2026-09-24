"""Diagnostic-integrity verdicts.

Every command result carries ``verdict``:

- ``PASS``    — the target was tested and every finding is valid and clean;
- ``FAIL``    — the target was tested and something is wrong;
- ``UNKNOWN`` — the target could not be meaningfully tested.

Missing evidence must never become negative evidence: UNKNOWN is not PASS.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_BLOCKED = 2
EXIT_UNKNOWN = 3


def from_counts(*, clean: int, problem: int, inconclusive: int) -> str:
    """Verdict for a probe run. Any problem → FAIL; PASS needs clean probes and nothing unresolved."""
    if problem > 0:
        return FAIL
    if clean > 0 and inconclusive == 0:
        return PASS
    return UNKNOWN


def exit_code(result: Mapping[str, Any]) -> int:
    if result.get("blocked"):
        return EXIT_BLOCKED
    verdict = result.get("verdict")
    if verdict == UNKNOWN:
        return EXIT_UNKNOWN
    if verdict == FAIL:
        return EXIT_FAIL
    if verdict == PASS:
        return EXIT_PASS
    # Non-diagnostic commands (issues, contribute, …) use ok/not-ok.
    return EXIT_PASS if result.get("ok", False) else EXIT_FAIL


def line(verdict: str, reason: str = "") -> str:
    return f"Verdict: {verdict}" + (f" — {reason}" if reason else "")
