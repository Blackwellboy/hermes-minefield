"""Hermes plugin register(ctx) entrypoint."""

from __future__ import annotations

import atexit
import logging
from typing import Any

from . import agent_tool, auto_lite
from .commands.cli import minefield_command, register_cli
from .commands.dispatch import handle_slash
from .config import load_plugin_config, set_plugin_id
from .recorder import hooks as rec_hooks
from .recorder.store import get_recorder

logger = logging.getLogger(__name__)


def _hook_supported(name: str) -> bool:
    try:
        from hermes_cli.plugins import VALID_HOOKS
    except Exception:
        return True  # not inside Hermes (tests/tools): nothing to check against
    return name in VALID_HOOKS


def register(ctx: Any) -> None:
    """Opt-in Hermes plugin registration. Does not modify Hermes core."""
    set_plugin_id(getattr(ctx, "plugin_id", None))
    cfg = load_plugin_config()
    rec = get_recorder(
        retention_seconds=cfg.recorder_retention_seconds,
        max_events=cfg.recorder_max_events,
        max_bytes=cfg.recorder_max_bytes,
        persist=True,
    )
    # Write pending recorder events on unload/reload and on interpreter exit.
    atexit.register(rec.stop)
    if hasattr(ctx, "on_unload"):
        try:
            ctx.on_unload(rec.stop)
        except Exception:
            logger.debug("on_unload registration failed", exc_info=True)

    ctx.register_cli_command(
        name="minefield",
        help="Model Serving Minefield diagnostics & incident analysis",
        setup_fn=register_cli,
        handler_fn=minefield_command,
        description=(
            "Lite check, full Doctor, flight-recorder WTF analysis, and "
            "review-gated contribution/issue workflows."
        ),
    )

    ctx.register_command(
        "minefield",
        handler=handle_slash,
        description="Minefield: check | doctor | wtf | contribute | issues | status",
        args_hint="check|doctor|wtf|contribute|issues|status",
    )

    # Flight recorder hooks — metadata only; never block the agent.
    def _safe(fn):
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                logger.debug("minefield recorder hook error", exc_info=True)
                return None

        return wrapper

    ctx.register_hook("pre_tool_call", _safe(rec_hooks.on_pre_tool_call))
    ctx.register_hook("post_tool_call", _safe(rec_hooks.on_post_tool_call))
    ctx.register_hook("pre_llm_call", _safe(rec_hooks.on_pre_llm_call))
    ctx.register_hook("post_llm_call", _safe(rec_hooks.on_post_llm_call))
    ctx.register_hook("pre_api_request", _safe(rec_hooks.on_pre_api_request))
    ctx.register_hook("post_api_request", _safe(rec_hooks.on_post_api_request))
    ctx.register_hook("api_request_error", _safe(rec_hooks.on_api_request_error))

    def _on_session_start(**kwargs):
        rec_hooks.on_session_start(**kwargs)
        auto_lite.maybe_start()  # no-op unless auto_lite: true; never blocks

    ctx.register_hook("on_session_start", _safe(_on_session_start))
    ctx.register_hook("on_session_end", _safe(rec_hooks.on_session_end))
    ctx.register_hook("on_session_finalize", _safe(rec_hooks.on_session_finalize))
    # Newer hook (not in Hermes 0.21.0): register only where this Hermes knows it.
    if _hook_supported("agent_loop_stopped"):
        ctx.register_hook("agent_loop_stopped", _safe(rec_hooks.on_agent_loop_stopped))

    # Read-only diagnosis tool; hidden from the model unless expose_agent_tool: true.
    ctx.register_tool(
        name=agent_tool.TOOL_NAME,
        toolset=agent_tool.TOOLSET,
        schema=agent_tool.SCHEMA,
        handler=agent_tool.handler,
        check_fn=agent_tool.available,
        description=agent_tool.SCHEMA["description"],
    )

    logger.info("hermes-minefield plugin registered (auto_lite=%s)", cfg.auto_lite)
