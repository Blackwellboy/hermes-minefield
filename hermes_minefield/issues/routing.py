"""Deterministic SAFE GitHub target recommendation from incident classification.

Recommended repo != approval. Model output cannot choose the repository.
Ambiguous ownership → no recommendation; user must select.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

# Canonical allowlisted destinations (recommendation candidates only).
REPO_HERMES = "NousResearch/hermes-agent"
REPO_LLAMA = "ggerganov/llama.cpp"
REPO_MINEFIELD = "Blackwellboy/model-serving-minefield"

HERMES_CLASSIFICATIONS = frozenset(
    {
        "HERMES_UI_ORCHESTRATION",
        "HERMES_ORCHESTRATION_BUG",
        "UI_RENDERING_BUG",
        "AGENT_LOOP",
        "AGENT_TOOL_LOOP",
        "TOOL_BUG",
    }
)

LLAMA_CLASSIFICATIONS = frozenset(
    {
        "MODEL_SERVER_BUG",
        "RUNTIME_BUG",
        "PERFORMANCE_CONTENTION",
    }
)

MINEFIELD_CLASSIFICATIONS = frozenset(
    {
        "KNOWN_MINEFIELD_TRAP",
        "POSSIBLE_NEW_MINEFIELD_CANDIDATE",
    }
)

# Explicitly do not guess for these.
AMBIGUOUS_CLASSIFICATIONS = frozenset(
    {
        "UNKNOWN",
        "CONFIGURATION_ERROR",
        "EXPECTED_BEHAVIOUR",
        "MODEL_BEHAVIOUR",
    }
)


@dataclass(frozen=True)
class TargetRecommendation:
    recommended_repo: Optional[str]
    user_selection_required: bool
    reason: str
    confidence: str  # HIGH | MEDIUM | LOW | NONE


def recommend_target_repo(
    *,
    classification: str,
    serving_failure: bool = False,
    is_engineering_bug: bool = False,
    is_minefield_trap: bool = False,
    kind: Optional[str] = None,
    allowlist: Optional[Sequence[str]] = None,
    model_suggested_repo: Optional[str] = None,
) -> TargetRecommendation:
    """Return a SAFE recommendation. Ignores hostile model_suggested_repo."""
    del model_suggested_repo  # MODEL_CANNOT_SELECT_REPO — never consulted
    allow = set(allowlist or (REPO_HERMES, REPO_LLAMA, REPO_MINEFIELD))
    cls = (classification or "").strip().upper()

    def _ok(repo: str, reason: str, confidence: str) -> TargetRecommendation:
        if repo not in allow:
            return TargetRecommendation(
                None,
                True,
                f"recommended {repo} but not in allowlist — user must select",
                "NONE",
            )
        return TargetRecommendation(repo, False, reason, confidence)

    # Explicit contribution kind overrides soft classification hints.
    if kind in {"minefield_trap", "trap", "2"}:
        return _ok(REPO_MINEFIELD, "contribution_kind=minefield_trap", "HIGH")
    if kind in {"product_bug", "product", "engineering", "1"} and cls in HERMES_CLASSIFICATIONS:
        return _ok(REPO_HERMES, "hermes_engineering_bug+kind=product", "HIGH")

    if cls in AMBIGUOUS_CLASSIFICATIONS or not cls:
        return TargetRecommendation(
            None,
            True,
            "ambiguous_or_unknown_ownership — user must select target",
            "NONE",
        )

    if is_minefield_trap or cls in MINEFIELD_CLASSIFICATIONS:
        return _ok(REPO_MINEFIELD, f"classification={cls}", "HIGH")

    if cls in HERMES_CLASSIFICATIONS:
        return _ok(REPO_HERMES, f"hermes_owned classification={cls}", "HIGH")

    if cls in LLAMA_CLASSIFICATIONS or (
        serving_failure and cls in {"MODEL_SERVER_BUG", "RUNTIME_BUG", "PERFORMANCE_CONTENTION"}
    ):
        return _ok(REPO_LLAMA, f"runtime/server classification={cls}", "MEDIUM")

    if serving_failure and not is_engineering_bug:
        # Serving failure without clear stack → do not guess
        return TargetRecommendation(
            None,
            True,
            "serving_failure_without_clear_stack_owner — user must select",
            "NONE",
        )

    if is_engineering_bug:
        # Engineering bug but not in Hermes set — still ask
        return TargetRecommendation(
            None,
            True,
            "engineering_bug_mixed_ownership — user must select",
            "NONE",
        )

    return TargetRecommendation(
        None,
        True,
        f"no_safe_mapping for classification={cls}",
        "NONE",
    )


def resolve_contribute_target(
    *,
    artifact: Mapping[str, Any],
    kind: Optional[str] = None,
    explicit_repo: Optional[str] = None,
    user_selected_repo: bool = False,
    allowlist: Optional[Sequence[str]] = None,
    model_suggested_repo: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve draft target for contribute --github.

    Returns keys:
      target_repo, recommended_repo, user_selection_required, reason,
      can_draft (False when no repo chosen and selection required)
    """
    allow = tuple(allowlist or (REPO_HERMES, REPO_LLAMA, REPO_MINEFIELD))
    # Hostile model suggestion is intentionally discarded.
    rec = recommend_target_repo(
        classification=str(artifact.get("classification") or ""),
        serving_failure=bool(artifact.get("serving_failure")),
        is_engineering_bug=bool(artifact.get("is_engineering_bug")),
        is_minefield_trap=bool(artifact.get("is_minefield_trap")),
        kind=kind,
        allowlist=allow,
        model_suggested_repo=model_suggested_repo,
    )

    if explicit_repo:
        repo = explicit_repo.strip()
        if user_selected_repo or repo in set(allow):
            return {
                "target_repo": repo,
                "recommended_repo": rec.recommended_repo,
                "user_selection_required": False,
                "reason": "explicit_user_repo",
                "can_draft": True,
                "user_selected": True,
            }
        return {
            "target_repo": None,
            "recommended_repo": rec.recommended_repo,
            "user_selection_required": True,
            "reason": f"explicit repo {repo} not allowlisted and not marked user-selected",
            "can_draft": False,
            "user_selected": False,
        }

    if rec.recommended_repo and not rec.user_selection_required:
        return {
            "target_repo": rec.recommended_repo,
            "recommended_repo": rec.recommended_repo,
            "user_selection_required": False,
            "reason": rec.reason,
            "can_draft": True,
            "user_selected": False,
        }

    return {
        "target_repo": None,
        "recommended_repo": None,
        "user_selection_required": True,
        "reason": rec.reason,
        "can_draft": False,
        "user_selected": False,
    }
