"""Minefield contribution / candidate packet (no official trap numbers)."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from ..issues.sanitize import sanitize_packet
from ..paths import candidates_dir

LOCAL_OBSERVATION = "LOCAL_OBSERVATION"
CANDIDATE = "CANDIDATE"
NEEDS_REPRO = "NEEDS_REPRO"
REPRODUCED = "REPRODUCED"
DUPLICATE = "DUPLICATE"
ENGINEERING_BUG_NOT_TRAP = "ENGINEERING_BUG_NOT_TRAP"
REJECTED = "REJECTED"
MERGED_TRAP = "MERGED_TRAP"


@dataclass
class CandidatePacket:
    candidate_id: str
    created_at: float
    state: str
    kind: str  # product_bug | minefield_trap | unsure
    title: str
    summary: str
    incident_id: Optional[str] = None
    evidence: dict[str, Any] = field(default_factory=dict)
    official_trap_number: Optional[str] = None  # always None until maintainer acceptance
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_contribution_kind(
    *,
    serving_failure: bool,
    is_engineering_bug: bool,
    user_choice: Optional[str] = None,
) -> str:
    if user_choice in {"1", "product", "product_bug", "engineering"}:
        return "product_bug"
    if user_choice in {"2", "trap", "minefield", "minefield_trap"}:
        return "minefield_trap"
    if user_choice in {"3", "unsure"}:
        return "unsure"
    if is_engineering_bug and not serving_failure:
        return "product_bug"
    if serving_failure:
        return "minefield_trap"
    return "unsure"


def build_candidate(
    *,
    artifact: Mapping[str, Any],
    kind: Optional[str] = None,
    user_choice: Optional[str] = None,
) -> CandidatePacket:
    serving = bool(artifact.get("serving_failure"))
    eng = bool(artifact.get("is_engineering_bug"))
    resolved_kind = kind or classify_contribution_kind(
        serving_failure=serving, is_engineering_bug=eng, user_choice=user_choice
    )
    state = ENGINEERING_BUG_NOT_TRAP if resolved_kind == "product_bug" else CANDIDATE
    if resolved_kind == "unsure":
        state = NEEDS_REPRO

    packet = CandidatePacket(
        candidate_id=f"CAND-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}",
        created_at=time.time(),
        state=state,
        kind=resolved_kind,
        title=str(artifact.get("classification") or "candidate")
        + ": "
        + str(artifact.get("observed_symptom") or "")[:120],
        summary=str(artifact.get("likely_root_cause") or ""),
        incident_id=str(artifact.get("incident_id") or "") or None,
        evidence=sanitize_packet(
            {
                "execution": artifact.get("actual_execution_counts"),
                "repeated": artifact.get("repeated_call_counts"),
                "severity": artifact.get("severity"),
            }
        ),
        official_trap_number=None,  # OFFICIAL_TRAP_NUMBER_BEFORE_ACCEPTANCE=NO
        notes=[
            "OFFICIAL_TRAP_NUMBER_BEFORE_ACCEPTANCE=NO",
            "AUTOMATIC_UPLOAD=NO",
            "owner review required before any Minefield PR",
        ],
    )
    return packet


def save_candidate(packet: CandidatePacket) -> Path:
    path = candidates_dir() / f"{packet.candidate_id}.json"
    path.write_text(json.dumps(packet.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path
