"""Flight-recorder event schema (metadata-first)."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# Tool lifecycle — prepare ≠ execute
TOOL_PREPARED = "tool.prepared"
TOOL_REQUESTED = "tool.requested"
TOOL_EXECUTED = "tool.executed"
TOOL_COMPLETED = "tool.completed"
TOOL_FAILED = "tool.failed"

TURN_START = "turn.start"
TURN_END = "turn.end"
API_REQUEST = "api.request"
API_RESPONSE = "api.response"
API_ERROR = "api.error"
SESSION_START = "session.start"
SESSION_END = "session.end"
ORCH_RETRY = "orch.retry"
ORCH_RECOVERY = "orch.recovery"
ORCH_TIMEOUT = "orch.timeout"
ORCH_CANCEL = "orch.cancel"
UI_NOTE = "ui.note"


@dataclass
class RecorderEvent:
    type: str
    ts: float = field(default_factory=lambda: time.time())
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    session_id_hash: Optional[str] = None
    request_id_hash: Optional[str] = None
    tool_name: Optional[str] = None
    tool_arg_fingerprint: Optional[str] = None
    success: Optional[bool] = None
    result_bytes: Optional[int] = None
    finish_reason: Optional[str] = None
    content_len: Optional[int] = None
    reasoning_len: Optional[int] = None
    wall_ms: Optional[float] = None
    ttft_ms: Optional[float] = None
    http_status: Optional[int] = None
    error_class: Optional[str] = None
    model_hash: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Drop Nones for compact storage
        return {k: v for k, v in d.items() if v is not None and v != {}}
