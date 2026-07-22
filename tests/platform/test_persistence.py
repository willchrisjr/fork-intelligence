from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from fork_intelligence.db import Base
from fork_intelligence.models import AnalysisRun, Branch, Repository
from fork_intelligence.services.persistence import (
    BranchCandidate,
    record_branch_plan,
    record_credential_mode_transition,
)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


@pytest.fixture
def analysis(session: Session) -> AnalysisRun:
    run = AnalysisRun(requested_identifier="acme/repo", idempotency_key="idem-1")
    session.add(run)
    session.flush()
    return run


@pytest.fixture
def repository(session: Session) -> Repository:
    repo = Repository(
        github_id=1,
        owner="acme",
        name="repo",
        html_url="https://github.com/acme/repo",
        clone_url="https://github.com/acme/repo.git",
        default_branch="main",
    )
    session.add(repo)
    session.flush()
    return repo


def test_record_branch_plan_creates_new_branches(
    session: Session, analysis: AnalysisRun, repository: Repository
) -> None:
    retrieval_time = datetime.now(UTC)
    candidates = [
        BranchCandidate(
            name="main",
            is_default=True,
            priority=0,
            decision="selected",
            selection_reason="default_branch",
            head_sha="a" * 40,
            retrieval_time=retrieval_time,
        ),
        BranchCandidate(
            name="stale",
            is_default=False,
            priority=1,
            decision="unevaluated",
            selection_reason=None,
        ),
    ]

    persisted = record_branch_plan(
        session, analysis.id, repository.id, candidates, planner_version="2026.07.1"
    )

    assert {branch.name for branch in persisted} == {"main", "stale"}
    stored = session.scalars(select(Branch).where(Branch.analysis_id == analysis.id)).all()
    assert len(stored) == 2
    main = next(branch for branch in stored if branch.name == "main")
    assert main.decision == "selected"
    assert main.head_sha == "a" * 40
    assert main.retrieval_time == retrieval_time
    stale = next(branch for branch in stored if branch.name == "stale")
    assert stale.decision == "unevaluated"
    assert stale.head_sha is None


def test_record_branch_plan_updates_existing_branch_in_place(
    session: Session, analysis: AnalysisRun, repository: Repository
) -> None:
    record_branch_plan(
        session,
        analysis.id,
        repository.id,
        [
            BranchCandidate(
                name="main",
                is_default=True,
                priority=0,
                decision="unevaluated",
                selection_reason=None,
            )
        ],
        planner_version="2026.07.1",
    )

    record_branch_plan(
        session,
        analysis.id,
        repository.id,
        [
            BranchCandidate(
                name="main",
                is_default=True,
                priority=0,
                decision="selected",
                selection_reason="default_branch",
                head_sha="b" * 40,
                retrieval_time=datetime.now(UTC),
            )
        ],
        planner_version="2026.07.1",
    )

    stored = session.scalars(select(Branch).where(Branch.analysis_id == analysis.id)).all()
    assert len(stored) == 1
    assert stored[0].decision == "selected"
    assert stored[0].head_sha == "b" * 40


def test_record_branch_plan_scopes_by_planner_version(
    session: Session, analysis: AnalysisRun, repository: Repository
) -> None:
    for planner_version in ("2026.06.1", "2026.07.1"):
        record_branch_plan(
            session,
            analysis.id,
            repository.id,
            [
                BranchCandidate(
                    name="main",
                    is_default=True,
                    priority=0,
                    decision="unevaluated",
                    selection_reason=None,
                )
            ],
            planner_version=planner_version,
        )

    stored = session.scalars(select(Branch).where(Branch.analysis_id == analysis.id)).all()
    assert {branch.planner_version for branch in stored} == {"2026.06.1", "2026.07.1"}


def test_record_branch_plan_rejects_unsupported_decision(
    session: Session, analysis: AnalysisRun, repository: Repository
) -> None:
    with pytest.raises(ValueError, match="Unsupported branch decision"):
        record_branch_plan(
            session,
            analysis.id,
            repository.id,
            [
                BranchCandidate(
                    name="main",
                    is_default=True,
                    priority=0,
                    decision="maybe",  # type: ignore[arg-type]
                    selection_reason=None,
                )
            ],
            planner_version="2026.07.1",
        )


def test_record_branch_plan_requires_selection_reason_when_decided(
    session: Session, analysis: AnalysisRun, repository: Repository
) -> None:
    with pytest.raises(ValueError, match="selection_reason is required"):
        record_branch_plan(
            session,
            analysis.id,
            repository.id,
            [
                BranchCandidate(
                    name="main",
                    is_default=True,
                    priority=0,
                    decision="excluded",
                    selection_reason=None,
                )
            ],
            planner_version="2026.07.1",
        )


def test_record_branch_plan_requires_observed_fields_when_decided(
    session: Session, analysis: AnalysisRun, repository: Repository
) -> None:
    with pytest.raises(ValueError, match="head_sha and retrieval_time are required"):
        record_branch_plan(
            session,
            analysis.id,
            repository.id,
            [
                BranchCandidate(
                    name="main",
                    is_default=True,
                    priority=0,
                    decision="selected",
                    selection_reason="default_branch",
                )
            ],
            planner_version="2026.07.1",
        )


def test_record_credential_mode_transition_updates_mode_and_appends_history(
    session: Session, analysis: AnalysisRun
) -> None:
    assert analysis.credential_mode == "authenticated"
    assert analysis.credential_mode_transitions == []

    record_credential_mode_transition(
        session,
        analysis,
        to_mode="anonymous",
        reason="token_revoked",
        coverage_limitation="rate_limited_endpoints_skipped",
    )

    assert analysis.credential_mode == "anonymous"
    assert len(analysis.credential_mode_transitions) == 1
    transition = analysis.credential_mode_transitions[0]
    assert transition["from_mode"] == "authenticated"
    assert transition["to_mode"] == "anonymous"
    assert transition["reason"] == "token_revoked"
    assert transition["coverage_limitation"] == "rate_limited_endpoints_skipped"
    assert "occurred_at" in transition


def test_record_credential_mode_transition_is_noop_when_mode_unchanged(
    session: Session, analysis: AnalysisRun
) -> None:
    record_credential_mode_transition(session, analysis, to_mode="authenticated", reason="noop")

    assert analysis.credential_mode == "authenticated"
    assert analysis.credential_mode_transitions == []


def test_record_credential_mode_transition_rejects_unsupported_mode(
    session: Session, analysis: AnalysisRun
) -> None:
    with pytest.raises(ValueError, match="Unsupported credential mode"):
        record_credential_mode_transition(session, analysis, to_mode="ghost", reason="bad")
