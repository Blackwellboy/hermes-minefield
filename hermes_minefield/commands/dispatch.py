"""Shared CLI / slash dispatch.

Both surfaces parse with the same argparse tree (``cli.register_cli``) and run
through ``_guard``, so no exception ever escapes into Hermes: a slash-command
traceback would land in the user's chat.
"""

from __future__ import annotations

import argparse
import logging
import shlex
from collections.abc import Callable
from typing import Any

from ..cache import clear_cache
from .check import run_check
from .contribute import run_contribute
from .doctor import run_doctor
from .issues import run_issues
from .status import run_status
from .wtf import run_wtf

logger = logging.getLogger(__name__)

USAGE = (
    "Minefield commands:\n"
    "  /minefield status\n"
    "  /minefield check [--force] [--max-requests N]\n"
    "  /minefield doctor [--yes]\n"
    "  /minefield wtf [2m] [--session current|all|<id>]\n"
    "  /minefield incident [2m]\n"
    "  /minefield contribute [--incident ID] [--github --repo owner/name]\n"
    "  /minefield issues [--refresh]\n"
    "  /minefield clear-cache\n"
)


class UsageError(Exception):
    pass


class _SlashParser(argparse.ArgumentParser):
    """argparse that raises instead of printing + sys.exit (we're inside a chat)."""

    def error(self, message: str):  # type: ignore[override]
        raise UsageError(message)

    def exit(self, status: int = 0, message: str | None = None):  # type: ignore[override]
        raise UsageError(message or "")

    def print_help(self, file=None) -> None:  # -h / --help inside chat
        raise UsageError(self.format_help())


def _slash_parser() -> argparse.ArgumentParser:
    from .cli import register_cli

    parser = _SlashParser(prog="/minefield", add_help=False)
    register_cli(parser)
    return parser


def _guard(fn: Callable[..., dict[str, Any]], **kw: Any) -> dict[str, Any]:
    try:
        return fn(**kw)
    except (ValueError, PermissionError) as e:
        return {"ok": False, "text": f"minefield: {e}"}
    except Exception as e:
        logger.debug("minefield command failed", exc_info=True)
        return {
            "ok": False,
            "text": (
                f"minefield: internal error ({type(e).__name__}). "
                "Run with HERMES_PLUGINS_DEBUG=1 for details."
            ),
        }


def _clear_cache() -> dict[str, Any]:
    return {"ok": True, "text": f"Cleared {clear_cache()} fingerprint cache entries."}


def run_command(args: Any, *, surface: str = "cli") -> dict[str, Any]:
    """Dispatch a parsed namespace. ``surface`` is "cli" or "slash"."""
    cmd = getattr(args, "minefield_command", None)
    if not cmd:
        return {"ok": False, "text": USAGE}
    g = lambda name, default=None: getattr(args, name, default)  # noqa: E731
    if surface == "slash" and g("base_url"):
        # In gateway chats anyone in the room can type slash commands; letting them
        # point probes at arbitrary URLs would turn the host into a network scanner.
        return {
            "ok": False,
            "text": "minefield: --base-url is CLI-only. Run: hermes minefield "
            f"{cmd} --base-url <url>  (chat uses the configured Hermes model endpoint)",
        }
    if cmd == "status":
        return _guard(run_status, base_url=g("base_url"), model=g("model"))
    if cmd in {"check", "preflight"}:
        return _guard(
            run_check,
            base_url=g("base_url"),
            model=g("model"),
            max_requests=g("max_requests"),
            force=bool(g("force", False)),
            detect=not bool(g("no_detect", False)),
        )
    if cmd == "doctor":
        return _guard(
            run_doctor,
            base_url=g("base_url"),
            model=g("model"),
            yes=bool(g("yes", False)),
            max_requests=g("max_requests"),
        )
    if cmd in {"wtf", "incident"}:
        return _guard(run_wtf, window=g("window"), session=g("session"), save=g("save"))
    if cmd == "contribute":
        return _guard(
            run_contribute,
            incident_id=g("incident"),
            kind=g("kind"),
            github=bool(g("github", False)),
            target_repo=g("target_repo"),
            user_selected_repo=bool(g("target_repo")),
            approve=bool(g("i_approve_submit", False)),
            dry_run=not bool(g("submit", False)),
        )
    if cmd == "issues":
        return _guard(run_issues, limit=int(g("limit", 20) or 20), refresh=bool(g("refresh", False)))
    if cmd == "clear-cache":
        return _guard(_clear_cache)
    return {"ok": False, "text": f"unknown minefield command: {cmd}"}


def handle_cli(args: Any) -> dict[str, Any]:
    return run_command(args, surface="cli")


def slash_result(raw_args: str) -> dict[str, Any]:
    """Parse + run a slash command; returns the structured result."""
    raw = (raw_args or "").strip()
    if not raw:
        return {"ok": True, "text": USAGE}
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = raw.split()
    if parts:
        parts[0] = parts[0].lower()
    try:
        args = _slash_parser().parse_args(parts)
    except UsageError as e:
        msg = str(e).strip()
        if msg.startswith("usage:"):
            return {"ok": True, "text": msg}
        return {"ok": False, "text": f"minefield: {msg}\n\n{USAGE}"}
    result = run_command(args, surface="slash")
    if getattr(args, "json", False):
        from .cli import to_json

        return {**result, "text": to_json(result)}
    return result


def handle_slash(raw_args: str) -> str:
    """Hermes slash-command handler: ``/minefield <args>`` → text."""
    try:
        return slash_result(raw_args).get("text", "")
    except Exception:  # last line of defence — never raise into the chat
        logger.debug("minefield slash dispatch failed", exc_info=True)
        return "minefield: internal error. Run with HERMES_PLUGINS_DEBUG=1 for details."
