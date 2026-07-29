"""Read-model projections for provider access and branch-plan disclosure.

Kept separate from the route handlers so the mapping from durable records to
transport shapes is testable on its own, and so the sanitation rules live in
one place rather than being restated per endpoint.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fork_intelligence.models import AnalysisRun, Branch, Repository
from fork_intelligence.schemas import (
    QUOTA_SNAPSHOT_FIELDS,
    BranchPlanCounts,
    BranchPlanEntryRead,
    BranchPlanRead,
    CredentialModeTransitionRead,
    ProviderAccessRead,
    ProviderQuotaRead,
)

# Provider-access conditions that leave a run resumable rather than failed.
_ACCESS_CONDITION_CODES = frozenset(
    {"github_rate_limited", "github_unauthorized", "provider_access_exhausted"}
)


def project_provider_access(analysis: AnalysisRun) -> ProviderAccessRead:
    """Project provider-access provenance for one analysis.

    Every field is rebuilt from known keys; nothing is spread wholesale from a
    stored dict, so credential material cannot reach the response even if a
    future writer were to place it on the underlying record.
    """
    quota_raw = analysis.quota_snapshot or {}
    quota = ProviderQuotaRead(
        **{key: quota_raw.get(key) for key in QUOTA_SNAPSHOT_FIELDS if key in quota_raw}
    )

    transitions = [
        CredentialModeTransitionRead(
            from_mode=str(item.get("from_mode") or ""),
            to_mode=str(item.get("to_mode") or ""),
            reason=str(item.get("reason") or ""),
            coverage_limitation=_optional_str(item.get("coverage_limitation")),
            occurred_at=_optional_str(item.get("occurred_at")),
        )
        for item in analysis.credential_mode_transitions or []
        if isinstance(item, dict)
    ]

    # Distinct limitations, order preserved, so a repeated fallback does not
    # read as several different coverage problems.
    limitations: list[str] = []
    for transition in transitions:
        if transition.coverage_limitation and transition.coverage_limitation not in limitations:
            limitations.append(transition.coverage_limitation)
    for warning in analysis.warnings or []:
        if not isinstance(warning, dict):
            continue
        scope = warning.get("affected_scope")
        if isinstance(scope, str) and scope and scope not in limitations:
            limitations.append(scope)

    return ProviderAccessRead(
        credential_mode=analysis.credential_mode,
        quota=quota,
        transitions=transitions,
        coverage_limitations=limitations,
        access_condition=_access_condition(analysis),
    )


def _access_condition(analysis: AnalysisRun) -> dict[str, Any] | None:
    """Name the provider condition when no access mode could continue."""
    error = analysis.error
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    if code not in _ACCESS_CONDITION_CODES:
        return None
    return {
        "code": code,
        "message": _optional_str(error.get("message")),
        "credential_mode": _optional_str(error.get("credential_mode")),
        "resumable": True,
    }


def project_branch_plan(session: Session, analysis: AnalysisRun) -> BranchPlanRead:
    """Project analysis-level branch-plan counts, caps, version, and reasons.

    Aggregated in SQL rather than by loading every entry: an analysis can span
    many repositories, and the response must not grow with the candidate set.
    """
    sampling = analysis.sampling or {}
    planner_version = _optional_str(sampling.get("branch_planner_version"))

    rows = session.execute(
        select(Branch.decision, Branch.selection_reason, func.count())
        .where(Branch.analysis_id == analysis.id)
        .group_by(Branch.decision, Branch.selection_reason)
    ).all()

    counts = Counter[str]()
    reasons = Counter[str]()
    for decision, reason, total in rows:
        counts[decision] += total
        if reason:
            reasons[reason] += total

    excluded = counts.get("excluded", 0)
    unevaluated = counts.get("unevaluated", 0)
    considered = counts.get("selected", 0) + excluded + unevaluated

    return BranchPlanRead(
        planner_version=planner_version,
        effective_cap=_optional_int(sampling.get("branch_cap")),
        counts=BranchPlanCounts(
            considered=considered,
            selected=counts.get("selected", 0),
            excluded_by_cap=excluded,
            unevaluated=unevaluated,
            structurally_analyzed=_optional_int(sampling.get("branches_structurally_analyzed"))
            or 0,
        ),
        selection_reasons=dict(sorted(reasons.items())),
        structural_coverage_default_only=_optional_bool(
            sampling.get("structural_coverage_default_only")
        ),
    )


def project_repository_branch_plan(
    session: Session, analysis_id: uuid.UUID, repository_id: uuid.UUID
) -> list[BranchPlanEntryRead]:
    """Every considered candidate for one repository, in plan order."""
    rows = session.execute(
        select(Branch, Repository)
        .join(Repository, Repository.id == Branch.repository_id)
        .where(Branch.analysis_id == analysis_id, Branch.repository_id == repository_id)
        .order_by(Branch.planner_version, Branch.priority)
    ).all()
    return [
        BranchPlanEntryRead(
            repository_id=branch.repository_id,
            repository_full_name=f"{repository.owner}/{repository.name}",
            branch_name=branch.name,
            head_sha=branch.head_sha,
            is_default=branch.is_default,
            priority=branch.priority,
            decision=branch.decision,
            selection_reason=branch.selection_reason,
            retrieval_time=branch.retrieval_time,
            planner_version=branch.planner_version,
        )
        for branch, repository in rows
    ]


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
