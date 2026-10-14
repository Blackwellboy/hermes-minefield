"""A stand-in Hermes session process for the Gate A scenario suite.

    HERMES_HOME=... python tests/e2e/hermes_session.py <scenario> <session_id> [n]

Loads plugins through Hermes's own PluginManager (like a real Hermes process),
fires the scenario's hooks through Hermes's own ``invoke_hook`` with the kwargs
Hermes really sends, then exits normally so the plugin's atexit/on_unload
flush runs. A separate ``hermes minefield wtf`` process then reads the result.
"""

from __future__ import annotations

import json
import sys
import time


def tool_call(invoke, sid: str, i: int, tool: str, args: dict, result: str, *, status: str = "ok") -> None:
    ids = dict(
        task_id=sid, session_id=sid, tool_call_id=f"{sid}-c{i}", turn_id=f"{sid}-t", api_request_id=f"{sid}-r"
    )
    invoke("pre_tool_call", tool_name=tool, args=args, middleware_trace=[], **ids)
    invoke(
        "post_tool_call",
        tool_name=tool,
        args=args,
        result=result,
        duration_ms=5,
        status=status,
        error_type="tool_error" if status == "error" else None,
        error_message="boom" if status == "error" else None,
        middleware_trace=[],
        **ids,
    )


def api_round(invoke, sid: str, i: int) -> None:
    rid = f"{sid}-r{i}"
    t0 = time.time()
    invoke(
        "pre_api_request",
        task_id=sid,
        turn_id=f"{sid}-t",
        api_request_id=rid,
        session_id=sid,
        model="m",
        started_at=t0,
    )
    invoke(
        "post_api_request",
        task_id=sid,
        turn_id=f"{sid}-t",
        api_request_id=rid,
        session_id=sid,
        model="m",
        api_duration=0.8,
        started_at=t0,
        ended_at=t0 + 0.8,
        first_chunk_at=t0 + 0.2,
        finish_reason="tool_calls",
        assistant_content_chars=0,
        assistant_tool_call_count=1,
        response={"assistant_message": {"tool_calls": []}},
    )


def scenario(name: str, sid: str, n: int, invoke) -> None:
    invoke("on_session_start", session_id=sid, model="m", platform="cli")
    invoke(
        "pre_llm_call",
        session_id=sid,
        user_message="hi",
        conversation_history=[],
        is_first_turn=True,
        model="m",
        platform="cli",
    )
    if name == "normal":
        for i in range(n):
            api_round(invoke, sid, i)
            tool_call(
                invoke, sid, i, "read_file", {"path": f"src/m{i}.py"}, json.dumps({"content": f"module {i}"})
            )
        tool_call(invoke, sid, n, "write_file", {"path": "out.txt"}, json.dumps({"ok": True}))
    elif name == "errors":
        for i in range(n):
            tool_call(
                invoke,
                sid,
                i,
                "terminal",
                {"command": f"cmd-{i}"},
                json.dumps({"error": "exit 1"}),
                status="error",
            )
    elif name == "loop":
        for i in range(n):
            tool_call(invoke, sid, i, "search_files", {"pattern": "TODO"}, json.dumps({"matches": []}))
    else:
        raise SystemExit(f"unknown scenario {name}")
    invoke(
        "post_llm_call",
        session_id=sid,
        user_message="hi",
        assistant_response="done",
        conversation_history=[],
        model="m",
        platform="cli",
    )
    invoke("on_session_end", session_id=sid, completed=True, interrupted=False, model="m", platform="cli")


def main() -> int:
    name, sid = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    from hermes_cli import plugins as hp

    hp.discover_plugins(force=True)
    loaded = hp.get_plugin_manager()._plugins.get("hermes-minefield")
    if loaded is None or not loaded.enabled or loaded.error:
        print(f"plugin not loaded: {loaded and loaded.error}", file=sys.stderr)
        return 2

    def invoke(hook: str, **kw) -> None:
        results = hp.invoke_hook(hook, **kw)
        if any(r is not None for r in results):
            raise SystemExit(f"{hook} returned {results!r} (would be injected / act as a directive)")

    scenario(name, sid, n, invoke)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
