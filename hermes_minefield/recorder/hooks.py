"""Map Hermes plugin hooks → metadata-first recorder events.

Kwarg names follow Hermes's real fire sites (see docs/IMPROVEMENT_PLAN.md §2.1
and tests/fixtures/hermes_hook_payloads.json). Rules for every callback here:

- accept ``**kwargs`` and never raise (a raising ``pre_tool_call`` blocks the tool);
- return ``None`` (a ``pre_llm_call`` return value is injected into the prompt);
- record hashes, lengths, counts and enums only — never args, results,
  messages, prompts, error messages or URLs.
"""

from __future__ import annotations

import json
import math
from typing import Any

from ..privacy import arg_fingerprint, stable_hash
from .events import (
    API_ERROR,
    API_REQUEST,
    API_RESPONSE,
    ORCH_CANCEL,
    SESSION_END,
    SESSION_START,
    TOOL_COMPLETED,
    TOOL_EXECUTED,
    TOOL_FAILED,
    TOOL_PREPARED,
    TOOL_REQUESTED,
    TURN_END,
    TURN_FINISHED,
    TURN_START,
    RecorderEvent,
)
from .store import get_recorder


def _session_hash(kw: dict) -> str | None:
    sid = kw.get("session_id") or kw.get("task_id")
    if not sid:
        return None
    return stable_hash(str(sid), n=16)


def _req_hash(kw: dict) -> str | None:
    rid = kw.get("api_request_id") or kw.get("request_id")
    return stable_hash(str(rid), n=12) if rid else None


def _call_extra(kw: dict) -> dict[str, Any]:
    cid = kw.get("tool_call_id")
    return {"tool_call_id_hash": stable_hash(str(cid), n=12)} if cid else {}


try:  # Hermes >= 0.21.3; older versions can't tell us about guardrail refusals.
    from agent.tool_result_classification import is_guardrail_refusal as _is_guardrail_refusal
except Exception:  # pragma: no cover - depends on installed Hermes
    _is_guardrail_refusal = None


def _tool_name(tool_name: Any, kw: dict) -> str:
    return str(tool_name or kw.get("name") or "unknown")


def _tool_args(args: Any, kw: dict) -> Any:
    # Hermes sends ``args``; ``params`` is accepted for events from older callers.
    return args if args is not None else kw.get("params")


def _as_str(v: Any) -> str | None:
    return str(v) if v is not None else None


def _as_int(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _as_float(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _as_bool(v: Any) -> bool | None:
    return v if isinstance(v, bool) else None


def _enum_str(v: Any, *, max_len: int = 40) -> str | None:
    """Keep short identifier-like strings (error types, reasons); drop free text."""
    if not isinstance(v, str) or not v or len(v) > max_len:
        return None
    return v if all(c.isalnum() or c in "_.-" for c in v) else None


def _payload_len(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray)):
        return len(value)
    try:
        return len(json.dumps(value, default=str))
    except Exception:
        return None


def on_pre_tool_call(tool_name: str = "", args: Any = None, **kwargs) -> None:
    """Hermes is dispatching a tool call. Must stay trivial: Hermes fails closed on errors here."""
    kw = kwargs
    rec = get_recorder()
    sid = _session_hash(kw)
    name = _tool_name(tool_name, kw)
    fp = arg_fingerprint(_tool_args(args, kw))
    rec.record(
        RecorderEvent(
            type=TOOL_REQUESTED,
            session_id_hash=sid,
            request_id_hash=_req_hash(kw),
            tool_name=name,
            tool_arg_fingerprint=fp,
            extra=_call_extra(kw),
        )
    )


def _result_fingerprint(result: Any) -> str | None:
    if result is None:
        return None
    if isinstance(result, (str, bytes, bytearray)):
        return stable_hash(result, n=16)
    try:
        return stable_hash(json.dumps(result, sort_keys=True, default=str), n=16)
    except Exception:
        return None


def on_post_tool_call(tool_name: str = "", args: Any = None, result: Any = None, **kwargs) -> None:
    kw = kwargs
    rec = get_recorder()
    sid = _session_hash(kw)
    name = _tool_name(tool_name, kw)
    fp = arg_fingerprint(_tool_args(args, kw))
    status = kw.get("status")
    if isinstance(status, str) and status:
        success = status != "error"
        error_class = (_enum_str(kw.get("error_type")) or "error") if not success else None
    else:  # legacy callers passed an exception object
        err = kw.get("error") or kw.get("exception")
        success = err is None
        error_class = type(err).__name__ if err is not None else None
    result_bytes = _payload_len(result)
    result_fp = _result_fingerprint(result)
    wall_ms = _as_float(kw.get("duration_ms"))
    req = _req_hash(kw)
    extra = _call_extra(kw)
    if _is_guardrail_refusal is not None:
        try:
            extra["guardrail_refusal"] = bool(_is_guardrail_refusal(result))
        except Exception:
            pass

    rec.record(
        RecorderEvent(
            type=TOOL_EXECUTED,
            session_id_hash=sid,
            request_id_hash=req,
            tool_name=name,
            tool_arg_fingerprint=fp,
            result_fingerprint=result_fp,
            success=success,
            result_bytes=result_bytes,
            wall_ms=wall_ms,
            extra=extra,
        )
    )
    rec.record(
        RecorderEvent(
            type=TOOL_COMPLETED if success else TOOL_FAILED,
            session_id_hash=sid,
            request_id_hash=req,
            tool_name=name,
            tool_arg_fingerprint=fp,
            result_fingerprint=result_fp,
            success=success,
            result_bytes=result_bytes,
            error_class=error_class,
            extra=_call_extra(kw),
        )
    )


def on_pre_llm_call(**kwargs) -> None:
    kw = kwargs
    model = kw.get("model")
    get_recorder().record(
        RecorderEvent(
            type=TURN_START,
            session_id_hash=_session_hash(kw),
            model_hash=stable_hash(model, n=12) if model else None,
            request_id_hash=_req_hash(kw),
        )
    )
    return None


def on_post_llm_call(**kwargs) -> None:
    kw = kwargs
    content = kw.get("assistant_response")
    if content is None:
        content = kw.get("content") or kw.get("response")
    reasoning = kw.get("reasoning_content") or kw.get("reasoning")
    get_recorder().record(
        RecorderEvent(
            type=TURN_END,
            session_id_hash=_session_hash(kw),
            finish_reason=_enum_str(kw.get("finish_reason")),
            content_len=len(content) if isinstance(content, str) else None,
            reasoning_len=len(reasoning) if isinstance(reasoning, str) else None,
            request_id_hash=_req_hash(kw),
        )
    )


def on_pre_api_request(**kwargs) -> None:
    kw = kwargs
    extra: dict[str, Any] = {}
    for key in ("api_call_count", "retry_count", "message_count", "tool_count", "approx_input_tokens"):
        v = _as_int(kw.get(key))
        if v is not None:
            extra[key] = v
    get_recorder().record(
        RecorderEvent(
            type=API_REQUEST,
            session_id_hash=_session_hash(kw),
            model_hash=stable_hash(kw.get("model"), n=12) if kw.get("model") else None,
            request_id_hash=_req_hash(kw),
            extra=extra,
        )
    )


def _response_tool_calls(response: Any) -> list[tuple[str, str | None]]:
    """(tool name, call-id hash) for each tool call the model emitted. Names only —
    never arguments."""
    try:
        calls = response["assistant_message"]["tool_calls"]
    except (TypeError, KeyError):
        return []
    out: list[tuple[str, str | None]] = []
    for tc in calls if isinstance(calls, list) else []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function")
        name = fn.get("name") if isinstance(fn, dict) else tc.get("name")
        cid = tc.get("id")
        out.append((str(name or "unknown")[:80], stable_hash(str(cid), n=12) if cid else None))
    return out[:256]


def on_post_api_request(**kwargs) -> None:
    kw = kwargs
    duration_s = _as_float(kw.get("api_duration"))
    if duration_s is not None:
        wall_ms = duration_s * 1000.0
    else:
        wall_ms = _as_float(kw.get("wall_ms") or kw.get("duration_ms"))

    ttft_ms = None
    started, first = _as_float(kw.get("started_at")), _as_float(kw.get("first_chunk_at"))
    if started is not None and first is not None and first >= started:
        ttft_ms = (first - started) * 1000.0
    elif kw.get("ttft_ms") is not None:
        ttft_ms = _as_float(kw.get("ttft_ms"))

    content_len = _as_int(kw.get("assistant_content_chars"))
    if content_len is None:
        content_len = _as_int(kw.get("content_len"))

    extra: dict[str, Any] = {}
    n_calls = _as_int(kw.get("assistant_tool_call_count"))
    if n_calls is not None:
        extra["tool_calls_requested"] = n_calls

    rec = get_recorder()
    sid, req = _session_hash(kw), _req_hash(kw)
    for call in _response_tool_calls(kw.get("response")):
        rec.record(
            RecorderEvent(
                type=TOOL_PREPARED,
                session_id_hash=sid,
                request_id_hash=req,
                tool_name=call[0],
                extra={"phase": "post_api_request", **({"tool_call_id_hash": call[1]} if call[1] else {})},
            )
        )
    rec.record(
        RecorderEvent(
            type=API_RESPONSE,
            session_id_hash=_session_hash(kw),
            request_id_hash=_req_hash(kw),
            http_status=_as_int(kw.get("status_code") or kw.get("http_status") or kw.get("status")),
            finish_reason=_enum_str(kw.get("finish_reason")),
            content_len=content_len,
            reasoning_len=_as_int(kw.get("reasoning_len")),
            wall_ms=wall_ms,
            ttft_ms=ttft_ms,
            extra=extra,
        )
    )


def on_api_request_error(**kwargs) -> None:
    kw = kwargs
    err = kw.get("error") or kw.get("exception")
    if isinstance(err, dict):
        error_class = _enum_str(err.get("type"), max_len=80) or "error"
    elif isinstance(err, BaseException):
        error_class = type(err).__name__
    else:
        error_class = _enum_str(kw.get("error_class"), max_len=80) or "error"

    extra: dict[str, Any] = {}
    retryable = _as_bool(kw.get("retryable"))
    if retryable is not None:
        extra["retryable"] = retryable
    retry_count = _as_int(kw.get("retry_count"))
    if retry_count is not None:
        extra["retry_count"] = retry_count
    reason = _enum_str(kw.get("reason"))
    if reason:
        extra["reason"] = reason
    duration_s = _as_float(kw.get("api_duration"))

    get_recorder().record(
        RecorderEvent(
            type=API_ERROR,
            session_id_hash=_session_hash(kw),
            request_id_hash=_req_hash(kw),
            error_class=error_class,
            http_status=_as_int(kw.get("status_code") or kw.get("status") or kw.get("http_status")),
            wall_ms=duration_s * 1000.0 if duration_s is not None else None,
            extra=extra,
        )
    )


def on_session_start(**kwargs) -> None:
    get_recorder().record(RecorderEvent(type=SESSION_START, session_id_hash=_session_hash(kwargs)))


def on_session_end(**kwargs) -> None:
    """Hermes fires this at the end of *every turn* (run_conversation), not per session."""
    kw = kwargs
    extra: dict[str, Any] = {}
    for key in ("completed", "interrupted", "failed"):
        v = _as_bool(kw.get(key))
        if v is not None:
            extra[key] = v
    rec = get_recorder()
    rec.record(RecorderEvent(type=TURN_FINISHED, session_id_hash=_session_hash(kw), extra=extra))
    # Ask the background flusher to write now, so a later `hermes minefield wtf`
    # in a fresh process sees this turn. No file I/O on the hook thread.
    rec.request_flush()


def on_session_finalize(**kwargs) -> None:
    """Real session teardown (/new, quit)."""
    rec = get_recorder()
    rec.record(RecorderEvent(type=SESSION_END, session_id_hash=_session_hash(kwargs)))
    rec.request_flush()


def on_agent_loop_stopped(**kwargs) -> None:
    """A turn was interrupted mid-run (gateway /stop, /new). Reason kept only if enum-like."""
    reason = _enum_str(kwargs.get("reason"))
    get_recorder().record(
        RecorderEvent(
            type=ORCH_CANCEL,
            extra={"interrupted": True, **({"reason": reason} if reason else {})},
        )
    )
