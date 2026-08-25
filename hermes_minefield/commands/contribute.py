""" /minefield contribute — sanitized candidate + optional GitHub draft."""

from __future__ import annotations

from typing import Any, Optional

from ..config import load_plugin_config
from ..contribute.candidate import build_candidate, save_candidate
from ..incident.store import load_incident, list_incidents
from ..issues.dedupe import search_local
from ..issues.draft import build_issue_draft, save_draft
from ..issues.github_client import submit_issue
from ..issues.routing import resolve_contribute_target
from ..target import resolve_target


def run_contribute(
    *,
    incident_id: Optional[str] = None,
    kind: Optional[str] = None,
    github: bool = False,
    target_repo: Optional[str] = None,
    user_selected_repo: bool = False,
    approve: bool = False,
    user_reply: Optional[str] = None,
    from_model: bool = False,
    model_suggested_repo: Optional[str] = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    cfg = load_plugin_config()
    art = None
    if incident_id:
        art = load_incident(incident_id)
    if not art:
        rows = list_incidents(limit=1)
        if rows:
            art = load_incident(rows[0].get("incident_id", "")) or rows[0]
    if not art:
        return {
            "ok": False,
            "text": "No incident found. Run /minefield wtf first.",
        }

    packet = build_candidate(artifact=art, user_choice=kind)
    path = save_candidate(packet)

    lines = [
        "Minefield contribute",
        f"  candidate: {packet.candidate_id}",
        f"  kind:      {packet.kind}",
        f"  state:     {packet.state}",
        f"  trap #:    (none — assigned only after maintainer acceptance)",
        f"  saved:     {path}",
        "",
        "What is this?",
        "  1. Product/runtime bug",
        "  2. Possible Minefield trap",
        "  3. Unsure, help classify",
        f"  (selected: {packet.kind})",
    ]

    hits = search_local(
        str(art.get("observed_symptom") or packet.title),
        known=list_incidents(limit=50),
    )
    if hits:
        lines.append("")
        lines.append("Possible duplicates:")
        for h in hits[:3]:
            lines.append(f"  [{h.match}] {h.issue_ref} — {h.title} ({h.status})")

    result: dict[str, Any] = {
        "ok": True,
        "candidate_id": packet.candidate_id,
        "path": str(path),
        "kind": packet.kind,
        "state": packet.state,
        "official_trap_number": None,
    }

    if github:
        route = resolve_contribute_target(
            artifact=art,
            kind=kind or packet.kind,
            explicit_repo=target_repo,
            user_selected_repo=user_selected_repo or bool(target_repo),
            allowlist=cfg.repo_allowlist,
            model_suggested_repo=model_suggested_repo,
        )
        result["recommended_repo"] = route.get("recommended_repo")
        result["user_selection_required"] = route.get("user_selection_required")
        result["routing_reason"] = route.get("reason")

        if not route.get("can_draft"):
            lines.extend(
                [
                    "",
                    "GitHub target: NOT AUTOMATICALLY SELECTED",
                    f"  reason: {route.get('reason')}",
                    "  TARGET_REPO_RECOMMENDED=NONE",
                    "  USER_SELECTION_REQUIRED=YES",
                    "",
                    "Pick an allowlisted target explicitly, e.g.:",
                    "  /minefield contribute --github --repo NousResearch/hermes-agent",
                    "  /minefield contribute --github --repo ggerganov/llama.cpp",
                    "  /minefield contribute --github --repo Blackwellboy/model-serving-minefield",
                    "",
                    "(Recommended repo != approval. No automatic upload.)",
                ]
            )
            result["target_repo"] = None
            result["text"] = "\n".join(lines)
            return result

        repo = route["target_repo"]
        try:
            env = {}
            try:
                t = resolve_target()
                env = {"model": t.model, "provider": t.provider, "base_url": t.base_url}
            except Exception:
                pass
            draft = build_issue_draft(artifact=art, target_repo=repo, environment=env)
            dpath = save_draft(draft)
            lines.extend(
                [
                    "",
                    "GitHub issue draft (NOT SUBMITTED):",
                    f"  recommended: {route.get('recommended_repo') or '(none)'}",
                    f"  target:      {repo}",
                    f"  routing:     {route.get('reason')}",
                    f"  title:       {draft.title}",
                    f"  draft:       {dpath}",
                    "",
                    "----- EXACT ISSUE BODY PREVIEW -----",
                    draft.body,
                    "----- END PREVIEW -----",
                    "",
                    f"Submit this issue to {repo}? [y/N]",
                    "(automatic upload is disabled; model approval is rejected)",
                    "(recommendation is not approval)",
                ]
            )
            result["draft_path"] = str(dpath)
            result["draft_body"] = draft.body
            result["target_repo"] = repo

            if approve or user_reply:
                sub = submit_issue(
                    repo=repo,
                    title=draft.title,
                    body=draft.body,
                    allowlist=cfg.repo_allowlist,
                    user_selected_repo=bool(route.get("user_selected"))
                    or user_selected_repo
                    or bool(target_repo),
                    user_reply=user_reply,
                    cli_approve=approve,
                    from_model=from_model,
                    dry_run=dry_run,
                )
                result["submit"] = {
                    "submitted": sub.submitted,
                    "url": sub.url,
                    "error": sub.error,
                    "dry_run": sub.dry_run,
                }
                if sub.submitted:
                    lines.append(
                        f"\nSubmit result: {'DRY-RUN OK' if sub.dry_run else 'SENT'} {sub.url}"
                    )
                else:
                    lines.append(f"\nSubmit blocked/failed: {sub.error}")
        except Exception as e:
            lines.append(f"\nGitHub draft failed: {type(e).__name__}: {e}")
            result["ok"] = False

    result["text"] = "\n".join(lines)
    return result
