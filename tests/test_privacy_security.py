from __future__ import annotations

from hermes_minefield.contribute.candidate import build_candidate
from hermes_minefield.privacy import redact_text, sanitize_mapping


def test_no_trap_prose_execution_import():
    # Guard: contribute/analyze never import minefield trap markdown as code.
    import hermes_minefield.incident.trap_match as tm
    import inspect

    src = inspect.getsource(tm)
    assert "exec(" not in src
    assert "eval(" not in src
    assert "compile(" not in src


def test_sanitize_mapping_drops_auth():
    cleaned = sanitize_mapping(
        {
            "Authorization": "Bearer SECRET",
            "ok": "fine",
            "nested": {"api_key": "x", "n": 1},
        }
    )
    assert cleaned["Authorization"] == "[REDACTED]"
    assert cleaned["nested"]["api_key"] == "[REDACTED]"
    assert cleaned["ok"] == "fine"


def test_candidate_never_assigns_trap_number():
    art = {
        "incident_id": "INC-1",
        "classification": "AGENT_TOOL_LOOP",
        "observed_symptom": "loop",
        "likely_root_cause": "loop",
        "serving_failure": False,
        "is_engineering_bug": True,
        "actual_execution_counts": {},
        "repeated_call_counts": {},
        "severity": "HIGH",
    }
    pkt = build_candidate(artifact=art, user_choice="2")
    assert pkt.official_trap_number is None
    assert "OFFICIAL_TRAP_NUMBER_BEFORE_ACCEPTANCE=NO" in pkt.notes


def test_home_paths_redacted():
    assert "/home/lagzilla" not in redact_text("see /home/lagzilla/secret/file.txt")
