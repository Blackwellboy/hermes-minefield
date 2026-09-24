"""Bounded incident storage + prune (plan T2.7) and incident id validation."""

from __future__ import annotations

import json
import os
import time

from hermes_minefield.commands.dispatch import slash_result
from hermes_minefield.incident.analyze import analyze_events
from hermes_minefield.incident.store import (
    INDEX_COMPACT_AT,
    INDEX_KEEP,
    list_incidents,
    load_incident,
    update_incident_status,
)
from hermes_minefield.paths import drafts_dir, incidents_dir


def _age(path, days):
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def _incident(days_old: float, **status):
    art = analyze_events([], persist=True)
    if status:
        update_incident_status(art.incident_id, **status)
    _age(incidents_dir() / f"{art.incident_id}.json", days_old)
    return art.incident_id


def test_prune_dry_run_then_real(tmp_hermes_home):
    old, new = _incident(100), _incident(1)
    draft = drafts_dir() / "draft-1-x.json"
    draft.write_text("{}")
    _age(draft, 100)

    dry = slash_result("prune --older-than 30d --dry-run")
    assert dry["incidents"] == [old] and dry["other"] == ["draft-1-x.json"]
    assert load_incident(old) is not None and draft.exists()

    real = slash_result("prune --older-than 30d")
    assert real["incidents"] == [old]
    assert load_incident(old) is None and not draft.exists()
    assert load_incident(new) is not None
    assert [r["incident_id"] for r in list_incidents()] == [new]


def test_linked_incidents_are_kept(tmp_hermes_home):
    linked = _incident(
        100,
        status="SUBMITTED",
        github={"repo": "a/b", "number": 1, "html_url": "https://github.com/a/b/issues/1"},
    )
    res = slash_result("prune --older-than 30d")
    assert res["kept_linked"] == [linked]
    assert load_incident(linked) is not None


def test_prune_rejects_tiny_windows(tmp_hermes_home):
    assert slash_result("prune --older-than 5m")["ok"] is False


def test_index_is_compacted(tmp_hermes_home):
    idx = incidents_dir() / "index.jsonl"
    idx.write_text(
        "".join(json.dumps({"incident_id": f"INC-00000000-{i:04X}"}) + "\n" for i in range(INDEX_COMPACT_AT))
    )
    analyze_events([], persist=True)
    assert len(idx.read_text().splitlines()) == INDEX_KEEP


def test_incident_id_path_traversal_is_rejected(tmp_hermes_home):
    secret = tmp_hermes_home / "secret.json"
    secret.write_text('{"classification": "stolen"}')
    assert load_incident("../../secret") is None
    assert load_incident("../secret") is None
    assert update_incident_status("../secret", "X") is False
