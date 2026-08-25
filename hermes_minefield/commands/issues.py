""" /minefield issues — local incidents + linked GitHub status."""

from __future__ import annotations

import re
from typing import Any, Optional

from ..incident.store import list_incidents, load_incident
from ..issues.github_client import refresh_issue_status


_GH_REF = re.compile(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)")


def run_issues(
    *,
    limit: int = 20,
    refresh: bool = False,
) -> dict[str, Any]:
    rows = list_incidents(limit=limit)
    lines = ["MINEFIELD ISSUES", ""]
    if not rows:
        lines.append("(no local incidents yet — try /minefield wtf)")
        return {"ok": True, "text": "\n".join(lines), "items": []}

    items = []
    for row in rows:
        iid = row.get("incident_id") or "?"
        full = load_incident(iid) or row
        title = (
            full.get("observed_symptom")
            or row.get("symptom")
            or full.get("classification")
            or "untitled"
        )
        classification = full.get("classification") or row.get("classification") or "?"
        status = full.get("status") or row.get("status") or "OBSERVED"
        gh = full.get("github") or full.get("github_issue")
        gh_line = "none"
        if isinstance(gh, dict):
            gh_line = gh.get("html_url") or f"{gh.get('repo')}#{gh.get('number')}"
            if refresh and gh.get("repo") and gh.get("number"):
                ref = refresh_issue_status(repo=gh["repo"], number=int(gh["number"]))
                mapped = ref.get("status") or "UNKNOWN"
                # closed not assumed fixed
                if mapped == "CLOSED":
                    status = "CLOSED"
                elif mapped == "FIXED":
                    status = "FIXED"
                elif mapped == "OPEN":
                    status = "OPEN"
                gh_line = f"{gh_line} [{mapped}]"
        elif isinstance(gh, str):
            gh_line = gh
            m = _GH_REF.search(gh)
            if refresh and m:
                ref = refresh_issue_status(repo=m.group(1), number=int(m.group(2)))
                mapped = ref.get("status") or "UNKNOWN"
                gh_line = f"{gh} [{mapped}]"
                if mapped == "CLOSED":
                    status = "CLOSED"

        trap = "—"
        matches = full.get("known_trap_matches") or []
        if matches:
            trap = str(matches[0].get("trap_id") or matches[0].get("title") or "match")
        cand = "candidate" if full.get("status") == "MINEFIELD_CANDIDATE" else "—"

        lines.extend(
            [
                f"{iid}",
                f"  {title[:100]}",
                f"  Classification: {classification}",
                f"  GitHub: {gh_line}",
                f"  Status: {status}",
                f"  Minefield trap/candidate: {trap} / {cand}",
                "",
            ]
        )
        items.append(
            {
                "incident_id": iid,
                "classification": classification,
                "status": status,
                "github": gh_line,
            }
        )

    lines.append("Note: CLOSED GitHub issues are not assumed FIXED without resolution evidence.")
    return {"ok": True, "text": "\n".join(lines), "items": items}
