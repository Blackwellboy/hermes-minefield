"""Network-free workspace shared by chat, Desktop and read-only tools.

No privileged action is available until a public host authority bridge has been
verified. Catalogue previews are deliberately distinct from executable plans.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from minefield.api import plan_checks


class Workspace:
    def home(self):
        return {
            "title": "Minefield",
            "state": "LOCAL_ONLY",
            "live_diagnostics": "ON_HOLD",
            "sharing": "OFF",
            "recipient": "No recipient configured",
            "last_result": "NOT_RUN",
            "choices": [
                {"id": "checks", "label": "Choose diagnostic checks", "effect": "Local catalogue preview"},
                {"id": "privacy", "label": "Privacy and contributions", "effect": "Local policy view"},
                {"id": "help", "label": "Help and coverage", "effect": "Local only"},
            ],
            "limitations": [
                "Trusted actor/session approval bridge is not yet host verified.",
                "No incident history is exposed on an unscoped surface.",
                "Fixture execution and receiver tests are not live qualification.",
            ],
        }

    def checks(self):
        # An inert, explicit placeholder avoids provider/config resolution.
        # detect=False is essential: a catalogue view must never issue GETs.
        plan = plan_checks(base_url="http://127.0.0.1:1/v1", mode="doctor", detect=False)
        return {
            "state": "NOT_RUN",
            "checks": [asdict(p) for p in plan.selected],
            "unavailable": [asdict(p) for p in plan.skipped],
            "generation_ceiling": plan.expected_requests,
            "http_ceiling": None,
            "note": "Catalogue estimates; not an approved execution plan.",
        }

    def preview(self, probe_ids):
        if type(probe_ids) is not list or not 1 <= len(probe_ids) <= 64:
            raise ValueError("select 1..64 named probes")
        if any(type(p) is not str or len(p) > 100 for p in probe_ids) or len(set(probe_ids)) != len(
            probe_ids
        ):
            raise ValueError("invalid probe selection")
        plan = plan_checks(base_url="http://127.0.0.1:1/v1", mode="doctor", detect=False, probe_ids=probe_ids)
        return {
            "state": "PREVIEW_ONLY",
            "selected": [asdict(p) for p in plan.selected],
            "skipped": [asdict(p) for p in plan.skipped],
            "generation_ceiling": plan.expected_requests,
            "http_ceiling": None,
            "target": "NOT_CONFIGURED",
            "requests": "Exact request preview not implemented",
            "approval_available": False,
            "reason": "Live hold; verified owner scope and exact request review required.",
        }

    def privacy(self):
        return {
            "sharing": "OFF",
            "recipient": "No recipient configured",
            "pending": 0,
            "model_summary": "Separate opt-in; ordinary chat provider may see returned summaries.",
            "automatic_contributions": "Fixture client and receiver implemented; host consent UI not verified.",
            "excluded": [
                "conversations",
                "tool arguments/results",
                "private names",
                "content hashes",
                "credentials",
            ],
            "deletion": "Fixture receipts support remote deletion. No production receiver configured.",
        }

    def action(self, action, payload=None):
        if action in {"home", "back", "cancel"}:
            return self.home()
        if action == "checks":
            return self.checks()
        if action == "privacy":
            return self.privacy()
        if action == "preview":
            if type(payload) is not dict or set(payload) != {"probe_ids"}:
                raise ValueError("invalid preview request")
            return self.preview(payload["probe_ids"])
        if action == "help":
            return {
                "text": "Choose checks to inspect current core catalogue costs. Preview never probes. "
                "Unknown evidence is not a pass. Approval, live probes and sharing remain unavailable "
                "until their host-bound pathways are verified."
            }
        raise PermissionError("action unavailable on this surface")


def render(view):
    if "choices" in view:
        return (
            "MINEFIELD\nLocal only | Sharing OFF | Live diagnostics ON HOLD\n"
            + "\n".join(f"/minefield {c['id']} — {c['label']} ({c['effect']})" for c in view["choices"])
            + "\nCompatibility: /minefield wtf [window] (legacy local incident view)."
            + "\nNo requests run. Trusted approval bridge is not yet available."
        )
    if "checks" in view:
        rows = [
            f"{p['id']}: at most {p['request_cost']} generation requests — {p['title']}"
            for p in view["checks"]
        ]
        return "CHECKS — NOT RUN\n" + "\n".join(rows) + "\n/minefield preview <probe-id> | /minefield back"
    return json.dumps(view, indent=2, ensure_ascii=True)


def command(raw):
    parts = raw.strip().split()
    action = parts[0] if parts else "home"
    payload = {"probe_ids": parts[1:]} if action == "preview" else None
    if action != "preview" and len(parts) > 1:
        raise ValueError("unexpected arguments")
    return render(Workspace().action(action, payload))
