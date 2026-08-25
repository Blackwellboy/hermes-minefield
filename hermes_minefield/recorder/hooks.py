"""Map Hermes plugin hooks → metadata-first recorder events."""

from __future__ import annotations

import time
from typing import Any, Optional

from ..privacy import arg_fingerprint, stable_hash
from .events import (
    API_ERROR,
    API_REQUEST,
    API_RESPONSE,
    RecorderEvent,
    SESSION_END,
    SESSION_START,
    TOOL_COMPLETED,
    TOOL_EXECUTED,
    TOOL_FAILED,
    TOOL_PREPARED,
    TOOL_REQUESTED,
    TURN_END,
    TURN_START,
)
from .store import get_recorder


def _session_hash(session_id: Any) -> Optional[str]:
    if not session_id:
        return None
    return stable_hash(str(session_id), n=16)


def _kw(kwargs: dict) -> dict:
    return kwargs or {}


def on_pre_tool_call(tool_name: str = "", params: Any = None, **kwargs) -> None:
    """PREPARED / REQUESTED — UI may render prepare without execution."""
    kw = _kw(kwargs)
    rec = get_recorder()
    sid = _session_hash(kw.get("session_id") or kw.get("task_id"))
    fp = arg_fingerprint(params)
    # Preparation signal (renderer may spam this)
    rec.record(
        RecorderEvent(
            type=TOOL_PREPARED,
            session_id_hash=sid,
            tool_name=str(tool_name or kw.get("name") or "unknown"),
            tool_arg_fingerprint=fp,
            extra={"phase": "pre_tool_call"},
        )
    )
    rec.record(
        RecorderEvent(
            type=TOOL_REQUESTED,
            session_id_hash=sid,
            tool_name=str(tool_name or kw.get("name") or "unknown"),
            tool_arg_fingerprint=fp,
            extra={"phase": "pre_tool_call"},
        )
    )


def on_post_tool_call(
    tool_name: str = "",
    params: Any = None,
    result: Any = None,
    **kwargs,
) -> None:
    kw = _kw(kwargs)
    rec = get_recorder()
    sid = _session_hash(kw.get("session_id") or kw.get("task_id"))
    fp = arg_fingerprint(params)
    name = str(tool_name or kw.get("name") or "unknown")
    err = kw.get("error") or kw.get("exception")
    success = err is None
    result_bytes = None
    if isinstance(result, (str, bytes, bytearray)):
        result_bytes = len(result)
    elif result is not None:
        try:
            import json

            result_bytes = len(json.dumps(result, default=str))
        except Exception:
            result_bytes = None

    rec.record(
        RecorderEvent(
            type=TOOL_EXECUTED,
            session_id_hash=sid,
            tool_name=name,
            tool_arg_fingerprint=fp,
            success=success,
            result_bytes=result_bytes,
        )
    )
    rec.record(
        RecorderEvent(
            type=TOOL_COMPLETED if success else TOOL_FAILED,
            session_id_hash=sid,
            tool_name=name,
            tool_arg_fingerprint=fp,
            success=success,
            result_bytes=result_bytes,
            error_class=type(err).__name__ if err else None,
        )
    )


def on_pre_llm_call(**kwargs) -> None:
    kw = _kw(kwargs)
    rec = get_recorder()
    sid = _session_hash(kw.get("session_id") or kw.get("task_id"))
    model = kw.get("model")
    rec.record(
        RecorderEvent(
            type=TURN_START,
            session_id_hash=sid,
            model_hash=stable_hash(model, n=12) if model else None,
            request_id_hash=stable_hash(kw.get("request_id"), n=12)
            if kw.get("request_id")
            else None,
        )
    )


def on_post_llm_call(**kwargs) -> None:
    kw = _kw(kwargs)
    rec = get_recorder()
    sid = _session_hash(kw.get("session_id") or kw.get("task_id"))
    content = kw.get("content") or kw.get("response") or ""
    reasoning = kw.get("reasoning_content") or kw.get("reasoning") or ""
    content_len = len(content) if isinstance(content, str) else None
    reasoning_len = len(reasoning) if isinstance(reasoning, str) else None
    rec.record(
        RecorderEvent(
            type=TURN_END,
            session_id_hash=sid,
            finish_reason=_as_str(kw.get("finish_reason")),
            content_len=content_len,
            reasoning_len=reasoning_len,
            wall_ms=_as_float(kw.get("wall_ms") or kw.get("duration_ms")),
            request_id_hash=stable_hash(kw.get("request_id"), n=12)
            if kw.get("request_id")
            else None,
        )
    )


def on_pre_api_request(**kwargs) -> None:
    kw = _kw(kwargs)
    rec = get_recorder()
    sid = _session_hash(kw.get("session_id") or kw.get("task_id"))
    rec.record(
        RecorderEvent(
            type=API_REQUEST,
            session_id_hash=sid,
            model_hash=stable_hash(kw.get("model"), n=12) if kw.get("model") else None,
            request_id_hash=stable_hash(kw.get("request_id"), n=12)
            if kw.get("request_id")
            else None,
            extra={"t0": time.time()},
        )
    )


def on_post_api_request(**kwargs) -> None:
    kw = _kw(kwargs)
    rec = get_recorder()
    sid = _session_hash(kw.get("session_id") or kw.get("task_id"))
    rec.record(
        RecorderEvent(
            type=API_RESPONSE,
            session_id_hash=sid,
            http_status=_as_int(kw.get("status") or kw.get("http_status")),
            finish_reason=_as_str(kw.get("finish_reason")),
            content_len=_as_int(kw.get("content_len")),
            reasoning_len=_as_int(kw.get("reasoning_len")),
            wall_ms=_as_float(kw.get("wall_ms") or kw.get("duration_ms")),
            ttft_ms=_as_float(kw.get("ttft_ms")),
            request_id_hash=stable_hash(kw.get("request_id"), n=12)
            if kw.get("request_id")
            else None,
        )
    )


def on_api_request_error(**kwargs) -> None:
    kw = _kw(kwargs)
    rec = get_recorder()
    sid = _session_hash(kw.get("session_id") or kw.get("task_id"))
    err = kw.get("error") or kw.get("exception")
    rec.record(
        RecorderEvent(
            type=API_ERROR,
            session_id_hash=sid,
            error_class=type(err).__name__ if err else _as_str(kw.get("error_class")) or "error",
            http_status=_as_int(kw.get("status") or kw.get("http_status")),
        )
    )


def on_session_start(**kwargs) -> None:
    kw = _kw(kwargs)
    get_recorder().record(
        RecorderEvent(
            type=SESSION_START,
            session_id_hash=_session_hash(kw.get("session_id")),
        )
    )


def on_session_end(**kwargs) -> None:
    kw = _kw(kwargs)
    get_recorder().record(
        RecorderEvent(
            type=SESSION_END,
            session_id_hash=_session_hash(kw.get("session_id")),
        )
    )


def _as_str(v: Any) -> Optional[str]:
    return str(v) if v is not None else None


def _as_int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except Exception:
        return None


def _as_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except Exception:
        return None
