"""Local incident artifact persistence."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from ..paths import atomic_write_text, candidates_dir, drafts_dir, incidents_dir
from .types import IncidentArtifact

INDEX_KEEP = 1000
INDEX_COMPACT_AT = 2000
# Only IDs we generate; anything else could be a path traversal (``../../x``).
_ID_RE = re.compile(r"^INC-\d{8}-[0-9A-F]{4,16}$")
# Statuses that tie an incident to an open upstream report: never prune those.
_PROTECTED_STATUSES = {"SUBMITTED", "OPEN"}


def valid_incident_id(incident_id: str) -> bool:
    return bool(_ID_RE.match(incident_id or ""))


def save_incident(artifact: IncidentArtifact) -> Path:
    path = incidents_dir() / f"{artifact.incident_id}.json"
    atomic_write_text(path, json.dumps(artifact.to_dict(), indent=2, sort_keys=True))
    # index
    idx = incidents_dir() / "index.jsonl"
    fd = os.open(idx, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "incident_id": artifact.incident_id,
                    "timestamp": artifact.timestamp,
                    "classification": artifact.classification,
                    "severity": artifact.severity,
                    "status": artifact.status,
                    "symptom": artifact.observed_symptom[:200],
                }
            )
            + "\n"
        )
    _compact_index(idx)
    return path


def _compact_index(idx: Path) -> None:
    try:
        lines = idx.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) > INDEX_COMPACT_AT:
        atomic_write_text(idx, "\n".join(lines[-INDEX_KEEP:]) + "\n")


def load_incident(incident_id: str) -> dict[str, Any] | None:
    if not valid_incident_id(incident_id):
        return None
    path = incidents_dir() / f"{incident_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_incidents(limit: int = 50) -> list[dict[str, Any]]:
    idx = incidents_dir() / "index.jsonl"
    if not idx.is_file():
        # fall back to scanning
        rows = []
        for p in sorted(incidents_dir().glob("INC-*.json"), reverse=True)[:limit]:
            try:
                rows.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return rows
    lines = idx.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    out.reverse()
    return out


def update_incident_status(incident_id: str, status: str, **fields: Any) -> bool:
    data = load_incident(incident_id)  # validates the id
    if not data:
        return False
    data["status"] = status
    data.update(fields)
    path = incidents_dir() / f"{incident_id}.json"
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True))
    return True


def prune(*, older_than_seconds: float, dry_run: bool = False, now: float | None = None) -> dict[str, Any]:
    """Delete local incidents, candidates and drafts older than the cutoff.

    Incidents linked to an upstream report (status SUBMITTED/OPEN, or with a
    ``github`` link that isn't closed) are kept.
    """
    now = time.time() if now is None else now
    cutoff = now - older_than_seconds
    removed: list[str] = []
    kept_linked: list[str] = []

    for p in sorted(incidents_dir().glob("INC-*.json")):
        try:
            if p.stat().st_mtime >= cutoff:
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        linked = data.get("status") in _PROTECTED_STATUSES or (
            isinstance(data.get("github"), dict) and data.get("status") not in {"CLOSED", "FIXED"}
        )
        if linked:
            kept_linked.append(p.stem)
            continue
        removed.append(p.stem)
        if not dry_run:
            p.unlink(missing_ok=True)

    other: list[str] = []
    for d, pattern in ((candidates_dir(), "CAND-*.json"), (drafts_dir(), "draft-*.json")):
        for p in sorted(d.glob(pattern)):
            try:
                old = p.stat().st_mtime < cutoff
            except OSError:
                continue
            if old:
                other.append(p.name)
                if not dry_run:
                    p.unlink(missing_ok=True)

    if removed and not dry_run:
        idx = incidents_dir() / "index.jsonl"
        gone = set(removed)
        try:
            rows = idx.read_text(encoding="utf-8").splitlines()
        except OSError:
            rows = []
        keep = []
        for line in rows:
            try:
                if json.loads(line).get("incident_id") in gone:
                    continue
            except ValueError:
                continue
            keep.append(line)
        atomic_write_text(idx, "\n".join(keep) + ("\n" if keep else ""))

    return {"incidents": removed, "other": other, "kept_linked": kept_linked, "dry_run": dry_run}
