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

_KNOWN_TYPES = frozenset(
    {
        TOOL_PREPARED,
        TOOL_REQUESTED,
        TOOL_EXECUTED,
        TOOL_COMPLETED,
        TOOL_FAILED,
        TURN_START,
        TURN_END,
        API_REQUEST,
        API_RESPONSE,
        API_ERROR,
        SESSION_START,
        SESSION_END,
        ORCH_RETRY,
        ORCH_RECOVERY,
        ORCH_TIMEOUT,
        ORCH_CANCEL,
        UI_NOTE,
    }
)


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

    def identity(self) -> str:
        """Stable dedupe key — prefer event_id; else metadata fingerprint (no private content)."""
        if self.event_id:
            return f"id:{self.event_id}"
        from ..privacy import stable_hash

        parts = (
            str(self.type),
            f"{float(self.ts):.6f}",
            self.session_id_hash or "",
            self.request_id_hash or "",
            self.tool_name or "",
            self.tool_arg_fingerprint or "",
            "" if self.success is None else str(bool(self.success)),
            "" if self.http_status is None else str(int(self.http_status)),
            self.finish_reason or "",
            self.error_class or "",
        )
        return "meta:" + stable_hash("|".join(parts), n=16)

    @classmethod
    def from_dict(cls, raw: Any, *, now: Optional[float] = None) -> Optional["RecorderEvent"]:
        """Parse one persisted row. Return None if schema-invalid / unsafe timestamp."""
        if not isinstance(raw, dict):
            return None
        etype = raw.get("type")
        if not isinstance(etype, str) or not etype:
            return None
        # Allow known types; also allow forward-compatible tool.*/api.*/orch.* prefixes
        if etype not in _KNOWN_TYPES and not (
            etype.startswith("tool.")
            or etype.startswith("api.")
            or etype.startswith("orch.")
            or etype.startswith("turn.")
            or etype.startswith("session.")
            or etype.startswith("ui.")
        ):
            return None
        try:
            ts = float(raw.get("ts"))
        except (TypeError, ValueError):
            return None
        now = time.time() if now is None else now
        # Reject clearly broken timestamps (far future / non-positive)
        if ts <= 0 or ts > now + 300:
            return None

        def _opt_str(key: str) -> Optional[str]:
            v = raw.get(key)
            if v is None:
                return None
            s = str(v)
            return s if s else None

        def _opt_int(key: str) -> Optional[int]:
            v = raw.get(key)
            if v is None:
                return None
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        def _opt_float(key: str) -> Optional[float]:
            v = raw.get(key)
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def _opt_bool(key: str) -> Optional[bool]:
            v = raw.get(key)
            if v is None:
                return None
            if isinstance(v, bool):
                return v
            return None

        extra = raw.get("extra")
        if not isinstance(extra, dict):
            extra = {}

        eid = _opt_str("event_id") or uuid.uuid4().hex[:16]
        return cls(
            type=etype,
            ts=ts,
            event_id=eid,
            session_id_hash=_opt_str("session_id_hash"),
            request_id_hash=_opt_str("request_id_hash"),
            tool_name=_opt_str("tool_name"),
            tool_arg_fingerprint=_opt_str("tool_arg_fingerprint"),
            success=_opt_bool("success"),
            result_bytes=_opt_int("result_bytes"),
            finish_reason=_opt_str("finish_reason"),
            content_len=_opt_int("content_len"),
            reasoning_len=_opt_int("reasoning_len"),
            wall_ms=_opt_float("wall_ms"),
            ttft_ms=_opt_float("ttft_ms"),
            http_status=_opt_int("http_status"),
            error_class=_opt_str("error_class"),
            model_hash=_opt_str("model_hash"),
            extra=extra,
        )
