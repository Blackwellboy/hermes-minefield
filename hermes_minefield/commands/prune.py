"""/minefield prune — delete old local incidents, candidates and drafts."""

from __future__ import annotations

from typing import Any

from ..config import load_plugin_config
from ..incident.store import prune
from .wtf import parse_window


def run_prune(*, older_than: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    cfg = load_plugin_config()
    default = cfg.incident_retention_days * 86400.0
    seconds = parse_window(older_than, default_seconds=default) if older_than else default
    if seconds < 3600:
        raise ValueError("--older-than must be at least 1h")
    res = prune(older_than_seconds=seconds, dry_run=dry_run)
    verb = "Would delete" if dry_run else "Deleted"
    lines = [
        f"Minefield prune (older than {seconds / 86400:.1f} days){' — DRY RUN' if dry_run else ''}",
        f"  {verb} {len(res['incidents'])} incident(s), {len(res['other'])} candidate/draft file(s)",
    ]
    if res["kept_linked"]:
        lines.append(f"  Kept {len(res['kept_linked'])} incident(s) linked to an open GitHub issue")
    return {"ok": True, "text": "\n".join(lines), **res}
