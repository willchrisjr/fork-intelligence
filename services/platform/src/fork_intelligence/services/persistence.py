from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from fork_intelligence.models import BRANCH_DECISIONS, CREDENTIAL_MODES, AnalysisRun, Branch

BranchDecision = Literal["selected", "excluded", "unevaluated"]


@dataclass(frozen=True)
class BranchCandidate:
    name: str
    is_default: bool
    priority: int
    decision: BranchDecision
    selection_reason: str | None
    head_sha: str | None = None
    retrieval_time: datetime | None = None


def record_credential_mode_transition(
    session: Session,
    analysis: AnalysisRun,
    *,
    to_mode: str,
    reason: str,
    coverage_limitation: str | None = None,
) -> None:
    if to_mode not in CREDENTIAL_MODES:
        raise ValueError(f"Unsupported credential mode: {to_mode}")
    if analysis.credential_mode == to_mode:
        return
    transition = {
        "from_mode": analysis.credential_mode,
        "to_mode": to_mode,
        "reason": reason,
        "coverage_limitation": coverage_limitation,
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    analysis.credential_mode_transitions = [*analysis.credential_mode_transitions, transition]
    analysis.credential_mode = to_mode
    session.add(analysis)


def record_branch_plan(
    session: Session,
    analysis_id: uuid.UUID,
    repository_id: uuid.UUID,
    candidates: Sequence[BranchCandidate],
    *,
    planner_version: str,
) -> list[Branch]:
    existing_by_name = {
        branch.name: branch
        for branch in session.scalars(
            select(Branch).where(
                Branch.analysis_id == analysis_id,
                Branch.repository_id == repository_id,
                Branch.planner_version == planner_version,
            )
        )
    }
    persisted: list[Branch] = []
    for candidate in candidates:
        if candidate.decision not in BRANCH_DECISIONS:
            raise ValueError(f"Unsupported branch decision: {candidate.decision}")
        if candidate.decision != "unevaluated" and not candidate.selection_reason:
            raise ValueError("selection_reason is required for selected or excluded candidates")
        if candidate.decision != "unevaluated" and (
            candidate.head_sha is None or candidate.retrieval_time is None
        ):
            raise ValueError("head_sha and retrieval_time are required for observed candidates")
        branch = existing_by_name.get(candidate.name)
        if branch is None:
            branch = Branch(
                analysis_id=analysis_id,
                repository_id=repository_id,
                planner_version=planner_version,
                name=candidate.name,
            )
            session.add(branch)
        branch.is_default = candidate.is_default
        branch.priority = candidate.priority
        branch.decision = candidate.decision
        branch.selection_reason = candidate.selection_reason
        branch.head_sha = candidate.head_sha
        branch.retrieval_time = candidate.retrieval_time
        persisted.append(branch)
    session.flush()
    return persisted
