"""Human-facing renderers for Lite / Doctor / status (structured data underneath)."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence


def _mark(level: str) -> str:
    lv = (level or "").upper()
    if lv in {"CLEAN", "OK", "PASS"}:
        return "✓"
    if lv in {"PROBLEM", "FAIL", "WARN", "WARNING"}:
        return "⚠"
    if lv in {"INCONCLUSIVE"}:
        return "?"
    if lv in {"SKIPPED", "NOT_APPLICABLE", "N/A", "NA"}:
        return "·"
    return "-"


def _finding_level(f: Any) -> str:
    if isinstance(f, Mapping):
        return str(f.get("level") or f.get("verdict") or "").upper()
    return str(getattr(f, "level", "") or getattr(f, "verdict", "") or "").upper()


def counts_from_findings(findings: Sequence[Any]) -> tuple[int, int, int]:
    """Derive CLEAN/PROBLEM/INCONCLUSIVE from finding levels.

    Minefield Doctor uses level ``OK`` for clean results.
    """
    clean = problem = inconclusive = 0
    for f in findings:
        lv = _finding_level(f)
        if lv in {"CLEAN", "OK", "PASS"}:
            clean += 1
        elif lv in {"PROBLEM", "FAIL", "WARN", "WARNING"}:
            problem += 1
        elif lv == "INCONCLUSIVE":
            inconclusive += 1
    return clean, problem, inconclusive


def extract_summary_counts(summary: Any) -> tuple[list[Any], int, int, int]:
    """Return (findings, clean, problem, inconclusive) with footer ≡ visible lines.

    Prefer Minefield Summary field names (``clean_count`` …). If structured
    counts are missing/zero while findings exist, derive counts from findings
    so cached bad entries still render correctly without re-running Lite.
    """
    findings: list[Any] = list(getattr(summary, "findings", None) or [])
    clean = problem = inconclusive = None

    if isinstance(summary, Mapping):
        findings = list(summary.get("findings") or findings)
        if "clean_count" in summary or "problem_count" in summary:
            clean = int(summary.get("clean_count") or 0)
            problem = int(summary.get("problem_count") or 0)
            inconclusive = int(summary.get("inconclusive_count") or 0)
        elif "clean" in summary or "problem" in summary:
            clean = int(summary.get("clean") or 0)
            problem = int(summary.get("problem") or 0)
            inconclusive = int(summary.get("inconclusive") or 0)
    else:
        if hasattr(summary, "clean_count"):
            clean = int(getattr(summary, "clean_count") or 0)
            problem = int(getattr(summary, "problem_count") or 0)
            inconclusive = int(getattr(summary, "inconclusive_count") or 0)
        elif hasattr(summary, "clean"):
            clean = int(getattr(summary, "clean") or 0)
            problem = int(getattr(summary, "problem") or 0)
            inconclusive = int(getattr(summary, "inconclusive") or 0)

    derived = counts_from_findings(findings)
    if clean is None or (
        findings
        and (clean, problem, inconclusive) == (0, 0, 0)
        and derived != (0, 0, 0)
    ):
        clean, problem, inconclusive = derived
    assert clean is not None and problem is not None and inconclusive is not None
    return findings, clean, problem, inconclusive


def render_lite_summary(
    summary: Any,
    *,
    requests: int,
    fingerprint_short: Optional[str] = None,
) -> str:
    findings, clean, problem, inconclusive = extract_summary_counts(summary)

    lines = ["Minefield Lite", ""]
    if fingerprint_short:
        lines[0] = f"Minefield Lite — fingerprint {fingerprint_short}"
    for f in findings:
        if isinstance(f, Mapping):
            level = f.get("level") or f.get("verdict") or ""
            title = f.get("title") or f.get("code") or ""
            detail = f.get("detail") or ""
        else:
            level = getattr(f, "level", "")
            title = getattr(f, "title", "") or getattr(f, "code", "")
            detail = getattr(f, "detail", "") or ""
        extra = f" — {detail}" if detail else ""
        lines.append(f"{_mark(str(level))} {title}{extra}")
    lines.extend(
        [
            "",
            f"{requests} requests",
            f"{clean} clean",
            f"{problem} warnings/problems",
            f"{inconclusive} inconclusive",
            "",
            "Run full Doctor?",
            "    /minefield doctor",
        ]
    )
    return "\n".join(lines)


def render_doctor_summary(summary: Any, *, requests: int) -> str:
    text = render_lite_summary(summary, requests=requests)
    return text.replace("Minefield Lite", "Minefield Doctor", 1).replace(
        "Run full Doctor?\n    /minefield doctor", "Doctor complete.", 1
    )


def render_status(
    *,
    fingerprint_short: Optional[str],
    cache_age: Optional[str],
    recorder_stats: Mapping[str, Any],
    last_summary: Optional[str] = None,
    auto_lite: str = "false",
    fingerprint_kind: str = "lite-cache (config-resolved)",
) -> str:
    lines = [
        "Minefield status",
        f"  fingerprint: {fingerprint_short or 'unknown'}  [{fingerprint_kind}]",
        f"  cache:       {cache_age or 'none'}",
        f"  auto_lite:   {auto_lite}",
        f"  recorder:    {recorder_stats.get('events_in_memory', 0)} in memory"
        + (
            f", {recorder_stats.get('persisted_recent', 0)} recent on disk"
            if "persisted_recent" in recorder_stats
            else ""
        ),
        f"  retention:   {recorder_stats.get('retention_seconds', '?')}s",
        f"  max_bytes:   {recorder_stats.get('max_bytes', '?')}",
    ]
    if last_summary:
        lines.extend(["", "Last check:", last_summary])
    return "\n".join(lines)
