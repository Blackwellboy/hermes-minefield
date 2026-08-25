"""Incident artifact schema and classification taxonomy."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# Classification taxonomy — engineering bugs ≠ Minefield traps
EXPECTED_BEHAVIOUR = "EXPECTED_BEHAVIOUR"
UI_RENDERING_BUG = "UI_RENDERING_BUG"
HERMES_ORCHESTRATION_BUG = "HERMES_ORCHESTRATION_BUG"
HERMES_UI_ORCHESTRATION = "HERMES_UI_ORCHESTRATION"
AGENT_LOOP = "AGENT_LOOP"
AGENT_TOOL_LOOP = "AGENT_TOOL_LOOP"
TOOL_BUG = "TOOL_BUG"
MODEL_BEHAVIOUR = "MODEL_BEHAVIOUR"
MODEL_SERVER_BUG = "MODEL_SERVER_BUG"
RUNTIME_BUG = "RUNTIME_BUG"
CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
PERFORMANCE_CONTENTION = "PERFORMANCE_CONTENTION"
KNOWN_MINEFIELD_TRAP = "KNOWN_MINEFIELD_TRAP"
POSSIBLE_NEW_MINEFIELD_CANDIDATE = "POSSIBLE_NEW_MINEFIELD_CANDIDATE"
UNKNOWN = "UNKNOWN"

SEVERITY_LOW = "LOW"
SEVERITY_ANNOYING = "ANNOYING"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_HIGH = "HIGH"
SEVERITY_CRITICAL = "CRITICAL"

STATUS_OBSERVED = "OBSERVED"
STATUS_TRIAGED = "TRIAGED"
STATUS_KNOWN_ISSUE = "KNOWN_ISSUE"
STATUS_NEEDS_REPRO = "NEEDS_REPRO"
STATUS_REPRODUCED = "REPRODUCED"
STATUS_ENGINEERING_BUG = "ENGINEERING_BUG"
STATUS_MINEFIELD_CANDIDATE = "MINEFIELD_CANDIDATE"
STATUS_MINEFIELD_TRAP = "MINEFIELD_TRAP"
STATUS_FIXED = "FIXED"
STATUS_CLOSED = "CLOSED"


@dataclass
class IncidentArtifact:
    incident_id: str
    timestamp: float
    session_id_hash: Optional[str]
    model_fingerprint: Optional[str]
    runtime_fingerprint: Optional[str]
    event_window: dict[str, Any]
    observed_symptom: str
    actual_execution_counts: dict[str, Any]
    repeated_call_counts: dict[str, Any]
    timings: dict[str, Any]
    errors: list[str]
    classification: str
    severity: str
    known_trap_matches: list[dict[str, Any]] = field(default_factory=list)
    known_issue_matches: list[dict[str, Any]] = field(default_factory=list)
    likely_root_cause: str = ""
    confidence: str = "MEDIUM"  # LOW|MEDIUM|HIGH — qualitative
    recommended_action: str = ""
    privacy_redactions: list[str] = field(default_factory=list)
    content_included_by_user: bool = False
    status: str = STATUS_OBSERVED
    serving_failure: bool = False
    is_minefield_trap: bool = False
    is_engineering_bug: bool = False
    raw_event_count: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def new_id() -> str:
        day = time.strftime("%Y%m%d", time.gmtime())
        return f"INC-{day}-{uuid.uuid4().hex[:4].upper()}"
