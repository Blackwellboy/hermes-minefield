"""``/minefield scan``: read-only static scan for known traps.

From chat it scans only the active Hermes config file: in a gateway chat anyone
in the room can type a slash command, and letting them name paths would turn
it into a file reader. From the CLI (``hermes minefield scan PATH ...``) you can
name any files or folders.
"""

from __future__ import annotations

import io
from typing import Any

from .. import verdict as V
from ..paths import hermes_home


def run_scan(*, paths: list[str] | None = None, surface: str = "cli") -> dict[str, Any]:
    if paths and surface == "slash":
        return {
            "ok": False,
            "text": "minefield: scanning named paths is CLI-only. Run: "
            "hermes minefield scan <path ...>  (chat scans your Hermes config)",
        }
    targets = list(paths or [str(hermes_home() / "config.yaml")])
    from minefield.registry import load_registry
    from minefield.render import render_scan
    from minefield.scan import scan

    report = scan(targets)
    if not report.get("accepted_paths"):
        return {
            "ok": False,
            "verdict": V.UNKNOWN,
            "text": f"minefield: nothing readable at {', '.join(targets)}\n\n"
            f"{V.line(V.UNKNOWN, 'nothing scanned')}",
        }
    titles = {
        e["id"]: {"title": e["title"], "source_path": e["source_path"]} for e in load_registry()["entries"]
    }
    # Possible traps are leads to check, not a failed test, so no FAIL verdict here.
    return {
        "ok": True,
        "scanned": targets,
        "accepted_paths": report.get("accepted_paths"),
        "findings": len(report.get("findings") or []),
        "text": render_scan(report, titles, stream=io.StringIO()).rstrip(),
    }
