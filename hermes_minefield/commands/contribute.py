"""/minefield contribute — sanitized candidate + optional GitHub draft.

Publication is always a deliberate human step:
- a draft is saved with the SHA-256 of its exact title+body; ``--submit-draft``
  sends exactly those bytes (tampered drafts are refused);
- real submission needs ``--i-approve-submit --submit``; from a chat surface it
  is refused unless ``allow_submit_from_chat`` is set (gateway rooms);
- remote duplicate search is opt-in and prints the terms before sending them.
"""

from __future__ import annotations

from typing import Any

from ..config import load_plugin_config
from ..contribute.candidate import build_candidate, save_candidate
from ..incident.store import list_incidents, load_incident, update_incident_status, valid_incident_id
from ..issues.dedupe import search_local
from ..issues.draft import DraftError, IssueDraft, build_issue_draft, load_draft, save_draft
from ..issues.github_client import dedupe_terms, parse_issue_url, search_issues, submit_issue
from ..issues.routing import resolve_contribute_target
from ..paths import hermes_home
from ..target import resolve_target

CHAT_SUBMIT_REFUSED = (
    "Real submission is CLI-only by default (anyone in a chat room can type slash commands).\n"
    "Run: hermes minefield contribute --submit-draft {draft} --i-approve-submit --submit\n"
    "(or set plugins.entries.hermes-minefield.settings.allow_submit_from_chat: true)"
)


def _display(path) -> str:
    """Show paths relative to HERMES_HOME (chat output shouldn't reveal the user's home dir)."""
    try:
        return "$HERMES_HOME/" + str(path.relative_to(hermes_home()))
    except ValueError:
        return path.name


def _resolve_incident(incident_id: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """(artifact, error). Never silently substitutes a different incident."""
    if incident_id:
        art = load_incident(incident_id) if valid_incident_id(incident_id) else None
        if art:
            return art, None
        recent = [r.get("incident_id") for r in list_incidents(limit=5)]
        hint = ", ".join(i for i in recent if i) or "none — run /minefield wtf first"
        return None, f"Incident {incident_id} not found. Recent: {hint}"
    rows = list_incidents(limit=1)
    art = load_incident(rows[0].get("incident_id", "")) if rows else None
    if not art:
        return None, "No incident found. Run /minefield wtf first."
    return art, None


def _link_incident(incident_id: str | None, url: str | None) -> dict[str, Any] | None:
    parsed = parse_issue_url(url)
    if not incident_id or not parsed:
        return None
    repo, number = parsed
    link = {"repo": repo, "number": number, "html_url": url}
    update_incident_status(incident_id, "SUBMITTED", github=link)
    return link


def _submit(
    draft: IssueDraft,
    *,
    lines: list[str],
    result: dict[str, Any],
    approve: bool,
    user_reply: str | None,
    from_model: bool,
    dry_run: bool,
    surface: str,
    draft_id: str,
    user_selected: bool,
) -> None:
    cfg = load_plugin_config()
    if not dry_run and surface != "cli" and not cfg.allow_submit_from_chat:
        lines.append("")
        lines.append(CHAT_SUBMIT_REFUSED.format(draft=draft_id))
        result["submit"] = {
            "submitted": False,
            "url": None,
            "error": "blocked:chat_submit_disabled",
            "dry_run": True,
        }
        return
    sub = submit_issue(
        repo=draft.target_repo or "",
        title=draft.title,
        body=draft.body,
        allowlist=cfg.repo_allowlist,
        user_selected_repo=user_selected,
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
        lines.append(f"\nSubmit result: {'DRY-RUN OK' if sub.dry_run else 'SENT'} {sub.url}")
        if not sub.dry_run:
            link = _link_incident(draft.incident_id, sub.url)
            if link:
                result["linked"] = link
                lines.append(f"Linked {draft.incident_id} → {link['repo']}#{link['number']}")
    else:
        lines.append(f"\nSubmit blocked/failed: {sub.error}")


def run_submit_draft(
    *,
    draft_id: str,
    approve: bool = False,
    user_reply: str | None = None,
    from_model: bool = False,
    dry_run: bool = True,
    surface: str = "cli",
) -> dict[str, Any]:
    """Submit a previously previewed draft, byte-for-byte."""
    try:
        draft = load_draft(draft_id)
    except DraftError as e:
        return {"ok": False, "text": f"minefield: {e}"}
    digest = draft.body_sha256[:12]
    lines = [
        "Minefield contribute — submit saved draft",
        f"  draft:   {draft_id} (sha256 {digest})",
        f"  target:  {draft.target_repo}",
        f"  title:   {draft.title}",
    ]
    result: dict[str, Any] = {"ok": True, "draft_id": draft_id, "body_sha256": draft.body_sha256}
    if not (approve or user_reply):
        lines.append(
            f"\nNot submitted. Re-run with --i-approve-submit (and --submit to send) to submit {digest}."
        )
    else:
        _submit(
            draft,
            lines=lines,
            result=result,
            approve=approve,
            user_reply=user_reply,
            from_model=from_model,
            dry_run=dry_run,
            surface=surface,
            draft_id=draft_id,
            user_selected=draft.user_selected_repo,
        )
    result["text"] = "\n".join(lines)
    return result


def run_contribute(
    *,
    incident_id: str | None = None,
    kind: str | None = None,
    github: bool = False,
    target_repo: str | None = None,
    user_selected_repo: bool = False,
    approve: bool = False,
    user_reply: str | None = None,
    from_model: bool = False,
    model_suggested_repo: str | None = None,
    dry_run: bool = True,
    submit_draft: str | None = None,
    remote_dedupe: bool | None = None,
    surface: str = "cli",
) -> dict[str, Any]:
    if submit_draft:
        return run_submit_draft(
            draft_id=submit_draft,
            approve=approve,
            user_reply=user_reply,
            from_model=from_model,
            dry_run=dry_run,
            surface=surface,
        )

    cfg = load_plugin_config()
    art, error = _resolve_incident(incident_id)
    if not art:
        return {"ok": False, "text": error}

    packet = build_candidate(artifact=art, user_choice=kind)
    path = save_candidate(packet)

    lines = ["Minefield contribute"]
    if not incident_id:
        lines.append(f"  using latest incident {art.get('incident_id')} (pass --incident to choose)")
    lines += [
        f"  candidate: {packet.candidate_id}",
        f"  kind:      {packet.kind}",
        f"  state:     {packet.state}",
        "  trap #:    (none — assigned only after maintainer acceptance)",
        f"  saved:     {_display(path)}",
        "",
        "What is this?",
        "  1. Product/runtime bug",
        "  2. Possible Minefield trap",
        "  3. Unsure, help classify",
        f"  (selected: {packet.kind})",
    ]

    hits = search_local(
        str(art.get("observed_symptom") or packet.title),
        known=[r for r in list_incidents(limit=50) if r.get("incident_id") != art.get("incident_id")],
    )
    if hits:
        lines.append("")
        lines.append("Possible duplicates:")
        for h in hits[:3]:
            lines.append(f"  [{h.match}] {h.issue_ref} — {h.title} ({h.status})")

    result: dict[str, Any] = {
        "ok": True,
        "incident_id": art.get("incident_id"),
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
        user_selected = bool(route.get("user_selected")) or user_selected_repo or bool(target_repo)
        try:
            env: dict[str, Any] = {}
            try:
                t = resolve_target()
                env = {"model": t.model, "provider": t.provider, "base_url": t.base_url}
            except Exception:
                pass
            draft = build_issue_draft(artifact=art, target_repo=repo, environment=env)
            draft.user_selected_repo = user_selected
            dpath = save_draft(draft)
            draft_id = dpath.stem
            lines.extend(
                [
                    "",
                    "GitHub issue draft (NOT SUBMITTED):",
                    f"  recommended: {route.get('recommended_repo') or '(none)'}",
                    f"  target:      {repo}",
                    f"  routing:     {route.get('reason')}",
                    f"  title:       {draft.title}",
                    f"  draft id:    {draft_id}",
                    f"  sha256:      {draft.body_sha256[:12]}",
                    "",
                    "----- EXACT ISSUE BODY PREVIEW -----",
                    draft.body,
                    "----- END PREVIEW -----",
                ]
            )

            use_remote = cfg.remote_dedupe if remote_dedupe is None else remote_dedupe
            if use_remote:
                terms = dedupe_terms(draft.title)
                lines += [
                    "",
                    f"Searching GitHub ({repo}) for these sanitized terms: {' '.join(terms) or '(none)'}",
                ]
                found = search_issues(repo=repo, terms=terms)
                result["remote_dedupe"] = {"terms": terms, **found}
                if found["ok"] and found["items"]:
                    lines.append("Possible upstream duplicates:")
                    for it in found["items"]:
                        lines.append(f"  #{it['number']} [{it['state']}] {it['title']}")
                elif found["ok"]:
                    lines.append("  (no similar upstream issues)")
                else:
                    lines.append("  (remote dedupe unavailable)")

            lines += [
                "",
                f"Submit this exact draft ({draft.body_sha256[:12]}) to {repo}?",
                f"  hermes minefield contribute --submit-draft {draft_id} --i-approve-submit --submit",
                "(automatic upload is disabled; model approval is rejected; recommendation is not approval)",
            ]
            result["draft_id"] = draft_id
            result["draft_path"] = str(dpath)
            result["draft_body"] = draft.body
            result["body_sha256"] = draft.body_sha256
            result["target_repo"] = repo

            if approve or user_reply:
                _submit(
                    draft,
                    lines=lines,
                    result=result,
                    approve=approve,
                    user_reply=user_reply,
                    from_model=from_model,
                    dry_run=dry_run,
                    surface=surface,
                    draft_id=draft_id,
                    user_selected=user_selected,
                )
        except Exception as e:
            lines.append(f"\nGitHub draft failed: {type(e).__name__}: {e}")
            result["ok"] = False

    result["text"] = "\n".join(lines)
    return result
