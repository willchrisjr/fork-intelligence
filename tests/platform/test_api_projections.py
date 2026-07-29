from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from fork_intelligence.api.projections import (
    project_branch_plan,
    project_provider_access,
    project_repository_branch_plan,
)
from fork_intelligence.db import Base
from fork_intelligence.models import AnalysisRun, Branch, Repository

TOKEN = "ghp-operator-secret"  # noqa: S105 - inert fixture value.


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


@pytest.fixture
def analysis(session: Session) -> AnalysisRun:
    run = AnalysisRun(
        requested_identifier="root/project",
        idempotency_key=f"idem-{uuid.uuid4()}",
    )
    session.add(run)
    session.flush()
    return run


def _repository(session: Session, github_id: int, owner: str, name: str) -> Repository:
    repo = Repository(
        github_id=github_id,
        owner=owner,
        name=name,
        html_url=f"https://github.com/{owner}/{name}",
        clone_url=f"https://github.com/{owner}/{name}.git",
        default_branch="main",
        is_fork=False,
        archived=False,
        disabled=False,
    )
    session.add(repo)
    session.flush()
    return repo


def _branch(
    session: Session,
    analysis: AnalysisRun,
    repo: Repository,
    name: str,
    *,
    decision: str,
    priority: int,
    reason: str | None,
    is_default: bool = False,
) -> Branch:
    branch = Branch(
        analysis_id=analysis.id,
        repository_id=repo.id,
        name=name,
        head_sha="a" * 40,
        is_default=is_default,
        priority=priority,
        decision=decision,
        selection_reason=reason,
        retrieval_time=datetime.now(UTC),
        planner_version="2026.07.2",
    )
    session.add(branch)
    session.flush()
    return branch


# --- Provider access ----------------------------------------------------------


def test_provider_access_projects_mode_quota_and_transitions(
    session: Session, analysis: AnalysisRun
) -> None:
    analysis.credential_mode = "anonymous"
    analysis.quota_snapshot = {
        "limit": 60,
        "remaining": 7,
        "reset": 123,
        "resource": "core",
        "credential_mode": "anonymous",
    }
    analysis.credential_mode_transitions = [
        {
            "from_mode": "authenticated",
            "to_mode": "anonymous",
            "reason": "operator_credential_quota_exhausted",
            "coverage_limitation": "Reduced fork census depth.",
            "occurred_at": "2026-07-22T00:00:00+00:00",
        }
    ]

    access = project_provider_access(analysis)

    assert access.credential_mode == "anonymous"
    assert access.quota.remaining == 7
    assert access.quota.resource == "core"
    assert len(access.transitions) == 1
    assert access.transitions[0].reason == "operator_credential_quota_exhausted"
    assert access.coverage_limitations == ["Reduced fork census depth."]


def test_provider_access_drops_unknown_quota_fields(
    session: Session, analysis: AnalysisRun
) -> None:
    """The transport shape must not grow to carry whatever a writer stored."""
    analysis.quota_snapshot = {
        "limit": 60,
        "remaining": 7,
        "smuggled": TOKEN,
        "authorization": f"Bearer {TOKEN}",
    }

    access = project_provider_access(analysis)
    serialized = access.model_dump_json()

    assert access.quota.limit == 60
    assert TOKEN not in serialized
    assert "smuggled" not in serialized


def test_provider_access_deduplicates_repeated_coverage_limitations(
    session: Session, analysis: AnalysisRun
) -> None:
    limitation = "Anonymous access lowers the rate limit."
    analysis.credential_mode_transitions = [
        {"from_mode": "authenticated", "to_mode": "anonymous", "reason": "a",
         "coverage_limitation": limitation},
        {"from_mode": "anonymous", "to_mode": "anonymous", "reason": "b",
         "coverage_limitation": limitation},
    ]

    access = project_provider_access(analysis)

    assert access.coverage_limitations == [limitation]
    assert len(access.transitions) == 2


def test_provider_access_names_the_resumable_condition_when_exhausted(
    session: Session, analysis: AnalysisRun
) -> None:
    analysis.credential_mode = "anonymous"
    analysis.error = {
        "code": "github_rate_limited",
        "message": "GitHub access could not continue.",
        "credential_mode": "anonymous",
    }

    access = project_provider_access(analysis)

    assert access.access_condition is not None
    assert access.access_condition["code"] == "github_rate_limited"
    assert access.access_condition["resumable"] is True


def test_provider_access_has_no_condition_on_an_unrelated_failure(
    session: Session, analysis: AnalysisRun
) -> None:
    analysis.error = {"code": "analysis_failed", "message": "boom"}

    assert project_provider_access(analysis).access_condition is None


# --- Branch plan --------------------------------------------------------------


def test_branch_plan_counts_separate_cap_exclusions_from_unevaluated(
    session: Session, analysis: AnalysisRun
) -> None:
    repo = _repository(session, 1, "root", "project")
    _branch(session, analysis, repo, "main", decision="selected", priority=0,
            reason="default_branch", is_default=True)
    _branch(session, analysis, repo, "a", decision="selected", priority=1, reason="recently_active")
    _branch(session, analysis, repo, "b", decision="excluded", priority=2,
            reason="branch_cap_exceeded")
    _branch(session, analysis, repo, "c", decision="unevaluated", priority=3,
            reason="probe_budget_exhausted")
    analysis.sampling = {
        "branch_cap": 2,
        "branch_planner_version": "2026.07.2",
        "branches_structurally_analyzed": 2,
        "structural_coverage_default_only": False,
    }
    session.flush()

    plan = project_branch_plan(session, analysis)

    assert plan.counts.considered == 4
    assert plan.counts.selected == 2
    # A sampling choice and missing data must never be conflated.
    assert plan.counts.excluded_by_cap == 1
    assert plan.counts.unevaluated == 1
    assert plan.counts.structurally_analyzed == 2
    assert plan.effective_cap == 2
    assert plan.planner_version == "2026.07.2"
    assert plan.structural_coverage_default_only is False


def test_branch_plan_summarizes_selection_reasons(
    session: Session, analysis: AnalysisRun
) -> None:
    repo = _repository(session, 1, "root", "project")
    _branch(session, analysis, repo, "main", decision="selected", priority=0,
            reason="default_branch", is_default=True)
    _branch(session, analysis, repo, "x", decision="excluded", priority=1,
            reason="branch_cap_exceeded")
    _branch(session, analysis, repo, "y", decision="excluded", priority=2,
            reason="branch_cap_exceeded")
    session.flush()

    plan = project_branch_plan(session, analysis)

    assert plan.selection_reasons == {"branch_cap_exceeded": 2, "default_branch": 1}


def test_branch_plan_is_empty_but_valid_before_planning_runs(
    session: Session, analysis: AnalysisRun
) -> None:
    plan = project_branch_plan(session, analysis)

    assert plan.counts.considered == 0
    assert plan.planner_version is None
    assert plan.selection_reasons == {}


def test_repository_branch_plan_lists_every_candidate_in_order(
    session: Session, analysis: AnalysisRun
) -> None:
    repo = _repository(session, 1, "someone", "fork")
    _branch(session, analysis, repo, "main", decision="selected", priority=0,
            reason="default_branch", is_default=True)
    _branch(session, analysis, repo, "feature", decision="excluded", priority=1,
            reason="branch_cap_exceeded")
    _branch(session, analysis, repo, "mystery", decision="unevaluated", priority=2,
            reason="probe_budget_exhausted")
    session.flush()

    entries = project_repository_branch_plan(session, analysis.id, repo.id)

    assert [entry.branch_name for entry in entries] == ["main", "feature", "mystery"]
    assert [entry.priority for entry in entries] == [0, 1, 2]
    assert entries[0].repository_full_name == "someone/fork"
    assert entries[0].is_default is True
    # Cap exclusion carries the cap reason; its position relative to the
    # selected branch is the priority.
    assert entries[1].decision == "excluded"
    assert entries[1].selection_reason == "branch_cap_exceeded"
    assert entries[1].priority > entries[0].priority
    # An unevaluated candidate names the missing input, not an exclusion.
    assert entries[2].decision == "unevaluated"
    assert entries[2].selection_reason == "probe_budget_exhausted"


def test_repository_branch_plan_is_scoped_to_its_repository(
    session: Session, analysis: AnalysisRun
) -> None:
    first = _repository(session, 1, "one", "repo")
    second = _repository(session, 2, "two", "repo")
    _branch(session, analysis, first, "main", decision="selected", priority=0,
            reason="default_branch", is_default=True)
    _branch(session, analysis, second, "main", decision="selected", priority=0,
            reason="default_branch", is_default=True)
    session.flush()

    entries = project_repository_branch_plan(session, analysis.id, first.id)

    assert len(entries) == 1
    assert entries[0].repository_full_name == "one/repo"
