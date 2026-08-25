"""Shared CLI / slash dispatch."""

from __future__ import annotations

import shlex
from typing import Any, Optional

from ..cache import clear_cache
from .check import run_check
from .contribute import run_contribute
from .doctor import run_doctor
from .issues import run_issues
from .status import run_status
from .wtf import run_wtf


def handle_cli(args: Any) -> dict[str, Any]:
    cmd = getattr(args, "minefield_command", None)
    if not cmd:
        return {
            "ok": False,
            "text": (
                "usage: hermes minefield {status,check,preflight,doctor,wtf,"
                "incident,contribute,issues,clear-cache}"
            ),
        }
    if cmd in {"status"}:
        return run_status(base_url=getattr(args, "base_url", None), model=getattr(args, "model", None))
    if cmd in {"check", "preflight"}:
        return run_check(
            base_url=getattr(args, "base_url", None),
            model=getattr(args, "model", None),
            max_requests=getattr(args, "max_requests", None),
            force=bool(getattr(args, "force", False)),
            detect=not bool(getattr(args, "no_detect", False)),
        )
    if cmd == "doctor":
        return run_doctor(
            base_url=getattr(args, "base_url", None),
            model=getattr(args, "model", None),
            yes=bool(getattr(args, "yes", False)),
            max_requests=getattr(args, "max_requests", None),
        )
    if cmd in {"wtf", "incident"}:
        return run_wtf(window=getattr(args, "window", None), session=getattr(args, "session", None))
    if cmd == "contribute":
        return run_contribute(
            incident_id=getattr(args, "incident", None),
            kind=getattr(args, "kind", None),
            github=bool(getattr(args, "github", False)),
            target_repo=getattr(args, "target_repo", None),
            user_selected_repo=bool(getattr(args, "target_repo", None)),
            approve=bool(getattr(args, "i_approve_submit", False)),
            dry_run=not bool(getattr(args, "submit", False)),
        )
    if cmd == "issues":
        return run_issues(
            limit=int(getattr(args, "limit", 20) or 20),
            refresh=bool(getattr(args, "refresh", False)),
        )
    if cmd == "clear-cache":
        n = clear_cache()
        return {"ok": True, "text": f"Cleared {n} fingerprint cache entries."}
    return {"ok": False, "text": f"unknown minefield command: {cmd}"}


def handle_slash(raw_args: str) -> str:
    raw = (raw_args or "").strip()
    if not raw:
        return (
            "Minefield commands:\n"
            "  /minefield status\n"
            "  /minefield check\n"
            "  /minefield doctor\n"
            "  /minefield wtf [2m]\n"
            "  /minefield incident [2m]\n"
            "  /minefield contribute [--github]\n"
            "  /minefield issues\n"
        )
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = raw.split()
    cmd = parts[0].lower() if parts else ""
    rest = parts[1:]

    def _flag(name: str) -> bool:
        return name in rest

    def _opt(name: str) -> Optional[str]:
        if name in rest:
            i = rest.index(name)
            if i + 1 < len(rest):
                return rest[i + 1]
        return None

    if cmd == "status":
        return run_status().get("text", "")
    if cmd in {"check", "preflight"}:
        mr = _opt("--max-requests")
        return run_check(
            max_requests=int(mr) if mr else None,
            force=_flag("--force"),
        ).get("text", "")
    if cmd == "doctor":
        return run_doctor(yes=_flag("--yes") or _flag("-y")).get("text", "")
    if cmd in {"wtf", "incident"}:
        window = rest[0] if rest and not rest[0].startswith("-") else None
        return run_wtf(window=window, session=_opt("--session")).get("text", "")
    if cmd == "contribute":
        return run_contribute(
            incident_id=_opt("--incident"),
            kind=_opt("--kind"),
            github=_flag("--github"),
            target_repo=_opt("--repo"),
            user_selected_repo=bool(_opt("--repo")),
            approve=_flag("--i-approve-submit"),
            dry_run=not _flag("--submit"),
        ).get("text", "")
    if cmd == "issues":
        return run_issues(refresh=_flag("--refresh")).get("text", "")
    if cmd == "clear-cache":
        n = clear_cache()
        return f"Cleared {n} fingerprint cache entries."
    return f"Unknown /minefield subcommand: {cmd}\nTry `/minefield` with no args for help."
