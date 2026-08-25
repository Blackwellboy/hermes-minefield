"""Lite footer counts must match visible finding classifications."""

from __future__ import annotations

from hermes_minefield.render import (
    counts_from_findings,
    extract_summary_counts,
    render_lite_summary,
)


def _live_like_summary():
    """Shape matching the live :8007 Lite run (and the buggy cache entry)."""
    findings = [
        {
            "level": "PROBLEM",
            "title": "unknown top-level field accepted HTTP 200",
            "detail": None,
        },
        {"level": "OK", "title": "reasoning_content", "detail": None},
        {"level": "OK", "title": "no orphaned close-think", "detail": None},
        {"level": "OK", "title": "thinking toggle separation", "detail": None},
        {"level": "OK", "title": "thinking default/on behaviour", "detail": None},
    ]
    # Legacy buggy cache: wrong field names → zeros, but findings present.
    return {
        "clean": 0,
        "problem": 0,
        "inconclusive": 0,
        "findings": findings,
        "requests_made": 5,
    }


def test_counts_from_findings_ok_and_problem():
    findings, clean, problem, inconclusive = extract_summary_counts(_live_like_summary())
    assert len(findings) == 5
    assert clean == 4
    assert problem == 1
    assert inconclusive == 0
    assert counts_from_findings(findings) == (4, 1, 0)


def test_render_footer_matches_visible_findings():
    text = render_lite_summary(_live_like_summary(), requests=5, fingerprint_short="e32966aeb446")
    lines = text.splitlines()
    visible = [ln for ln in lines if ln.startswith("✓") or ln.startswith("⚠") or ln.startswith("?")]
    assert len(visible) == 5
    assert "4 clean" in text
    assert "1 warnings/problems" in text
    assert "0 inconclusive" in text
    # Structured ↔ rendered contract
    findings, clean, problem, inconclusive = extract_summary_counts(_live_like_summary())
    assert len(visible) == len(findings)
    assert f"{clean} clean" in text
    assert f"{problem} warnings/problems" in text
    assert f"{inconclusive} inconclusive" in text


def test_minefield_summary_object_field_names():
    """Minefield API uses clean_count / problem_count / inconclusive_count."""

    class _F:
        def __init__(self, level, title):
            self.level = level
            self.title = title
            self.code = ""
            self.detail = None
            self.traps = ()

    class _S:
        clean_count = 4
        problem_count = 1
        inconclusive_count = 0
        findings = (
            _F("PROBLEM", "p"),
            _F("OK", "a"),
            _F("OK", "b"),
            _F("OK", "c"),
            _F("OK", "d"),
        )

    findings, clean, problem, inconclusive = extract_summary_counts(_S())
    assert (clean, problem, inconclusive) == (4, 1, 0)
    text = render_lite_summary(_S(), requests=5)
    assert "4 clean" in text
    assert "1 warnings/problems" in text


def test_check_summary_dict_uses_clean_count(monkeypatch, tmp_hermes_home):
    """Future cache writes must store non-zero counts from Minefield Summary."""
    from hermes_minefield.commands import check as check_mod

    class _F:
        level = "OK"
        code = "x"
        title = "t"
        detail = None
        traps = ()

    class _Summary:
        clean_count = 2
        problem_count = 1
        inconclusive_count = 0
        skipped_probe_count = 0
        findings = (
            type("P", (), {"level": "PROBLEM", "code": "", "title": "warn", "detail": None, "traps": ()})(),
            _F(),
            _F(),
        )

    class _Plan:
        selected_ids = ("a",)
        expected_requests = 1
        max_requests = 5

    class _Result:
        requests_executed = 3
        request_budget = 5

    monkeypatch.setattr(
        check_mod,
        "resolve_target",
        lambda **kw: type("T", (), {"model": "m", "base_url": "http://127.0.0.1:9/v1"})(),
    )

    import minefield.api as api

    monkeypatch.setattr(api, "plan_checks", lambda **kw: _Plan())
    monkeypatch.setattr(api, "run_checks", lambda plan, **kw: _Result())
    monkeypatch.setattr(api, "summarize", lambda result: _Summary())
    # Force path: no cache hit
    monkeypatch.setattr(check_mod, "get_entry", lambda key: None)
    stored = {}

    def _put(entry):
        stored["entry"] = entry

    monkeypatch.setattr(check_mod, "put_entry", _put)

    (tmp_hermes_home / "config.yaml").write_text(
        "model:\n  default: m\n  base_url: http://127.0.0.1:9/v1\n",
        encoding="utf-8",
    )
    out = check_mod.run_check(force=True, detect=False)
    assert out["summary"]["clean"] == 2
    assert out["summary"]["problem"] == 1
    assert "2 clean" in out["text"]
    assert "1 warnings/problems" in out["text"]
    assert stored["entry"].clean == 2
    assert stored["entry"].problem == 1
