"""Explicit human approval gate for GitHub submission.

MODEL OUTPUT CANNOT APPROVE.
Only direct user confirmation phrases (or CLI --i-approve-submit) count.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..privacy import looks_like_approval


@dataclass(frozen=True)
class ApprovalDecision:
    approved: bool
    reason: str


def evaluate_approval(
    *,
    user_reply: Optional[str] = None,
    cli_flag: bool = False,
    from_model: bool = False,
) -> ApprovalDecision:
    if from_model:
        return ApprovalDecision(False, "MODEL_CAN_APPROVE_UPLOAD=NO")
    if cli_flag:
        return ApprovalDecision(True, "cli_explicit_flag")
    if user_reply is not None and looks_like_approval(user_reply):
        return ApprovalDecision(True, "direct_user_yes")
    return ApprovalDecision(False, "no_explicit_user_approval")
