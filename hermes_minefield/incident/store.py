"""Local incident artifact persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..paths import atomic_write_text, incidents_dir
from .types import IncidentArtifact


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
    return path


def load_incident(incident_id: str) -> dict[str, Any] | None:
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
    data = load_incident(incident_id)
    if not data:
        return False
    data["status"] = status
    data.update(fields)
    path = incidents_dir() / f"{incident_id}.json"
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True))
    return True
