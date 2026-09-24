"""argparse tree for ``hermes minefield …``."""

from __future__ import annotations

import argparse


def register_cli(subparser: argparse.ArgumentParser) -> None:
    subs = subparser.add_subparsers(dest="minefield_command")

    p_status = subs.add_parser("status", help="Fingerprint, cache, recorder health")
    p_status.add_argument("--base-url")
    p_status.add_argument("--model")

    p_check = subs.add_parser("check", help="Minefield Lite (≤5 requests by default)")
    p_check.add_argument("--base-url")
    p_check.add_argument("--model")
    p_check.add_argument("--max-requests", type=int, default=None)
    p_check.add_argument("--force", action="store_true")
    p_check.add_argument("--no-detect", action="store_true")

    # Alias from design docs
    p_pre = subs.add_parser("preflight", help="Alias for check (Lite)")
    p_pre.add_argument("--base-url")
    p_pre.add_argument("--model")
    p_pre.add_argument("--max-requests", type=int, default=None)
    p_pre.add_argument("--force", action="store_true")

    p_doc = subs.add_parser("doctor", help="Full Doctor (explicit; single-slot guarded)")
    p_doc.add_argument("--base-url")
    p_doc.add_argument("--model")
    p_doc.add_argument("--yes", "-y", action="store_true")
    p_doc.add_argument("--max-requests", type=int, default=None)

    for name, help_text in (
        ("wtf", "Freeze flight recorder and explain weirdness"),
        ("incident", "Professional alias for wtf"),
    ):
        p = subs.add_parser(name, help=help_text)
        p.add_argument("window", nargs="?", default=None, help="e.g. 2m, 5m, 120s (default 5m)")
        p.add_argument("--session", default=None, help="current | all | <session id>")
        save = p.add_mutually_exclusive_group()
        save.add_argument(
            "--save", dest="save", action="store_true", default=None, help="always save the incident"
        )
        save.add_argument("--no-save", dest="save", action="store_false", help="never save the incident")

    p_con = subs.add_parser("contribute", help="Sanitized candidate / issue draft")
    p_con.add_argument("--incident")
    p_con.add_argument("--kind", choices=["1", "2", "3", "product", "trap", "unsure"])
    p_con.add_argument("--github", action="store_true")
    p_con.add_argument("--repo", dest="target_repo")
    p_con.add_argument(
        "--i-approve-submit",
        action="store_true",
        help="Explicit human approval to submit (still dry-run unless --submit)",
    )
    p_con.add_argument(
        "--submit",
        action="store_true",
        help="Actually submit after approval (default remains dry-run)",
    )

    p_iss = subs.add_parser("issues", help="List local incidents + linked GitHub status")
    p_iss.add_argument("--limit", type=int, default=20)
    p_iss.add_argument("--refresh", action="store_true")

    subs.add_parser("clear-cache", help="Clear fingerprint Lite cache")

    subparser.set_defaults(func=minefield_command)


def minefield_command(args: argparse.Namespace) -> int:
    from . import dispatch

    result = dispatch.handle_cli(args)
    text = result.get("text") or ""
    if text:
        print(text)
    from ..verdict import exit_code

    return exit_code(result)
