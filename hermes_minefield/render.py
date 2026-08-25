"""Human-facing renderers for Lite / Doctor / status (structured data underneath)."""

from __future__ import annotations

from typing import Any, Mapping, Optional


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


def render_lite_summary(
    summary: Any,
    *,
    requests: int,
    fingerprint_short: Optional[str] = None,
) -> str:
    findings = getattr(summary, "findings", None) or []
    if hasattr(summary, "clean"):
        clean = summary.clean
        problem = summary.problem
        inconclusive = summary.inconclusive
    elif isinstance(summary, Mapping):
        clean = summary.get("clean", 0)
        problem = summary.get("problem", 0)
        inconclusive = summary.get("inconclusive", 0)
        findings = summary.get("findings") or findings
    else:
        clean = problem = inconclusive = 0

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
) -> str:
    lines = [
        "Minefield status",
        f"  fingerprint: {fingerprint_short or 'unknown'}",
        f"  cache:       {cache_age or 'none'}",
        f"  auto_lite:   {auto_lite}",
        f"  recorder:    {recorder_stats.get('events_in_memory', 0)} events in memory",
        f"  retention:   {recorder_stats.get('retention_seconds', '?')}s",
        f"  max_bytes:   {recorder_stats.get('max_bytes', '?')}",
    ]
    if last_summary:
        lines.extend(["", "Last check:", last_summary])
    return "\n".join(lines)
