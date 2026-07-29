from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from fork_intelligence.config import Settings
from fork_intelligence.db import Base
from fork_intelligence.domain.branch_planning import BRANCH_PLANNER_VERSION
from fork_intelligence.errors import GitHubError
from fork_intelligence.models import (
    AnalysisRun,
    Branch,
    Repository,
    RepositoryNetwork,
    RepositorySnapshot,
    StageCheckpoint,
)
from fork_intelligence.services.pipeline import AnalysisPipeline

TOKEN = "ghp-operator-secret"  # noqa: S105 - inert fixture value.

ORIGINAL_HEAD = "a" * 40
MOVED_HEAD = "b" * 40
ACTIVITY = "2026-07-20T00:00:00Z"


class ResumeRouter:
    """GitHub boundary scripted with the heads a resumed run would observe."""

    def __init__(
        self,
        *,
        branches: dict[str, list[dict[str, str]]] | None = None,
        list_error: GitHubError | None = None,
    ) -> None:
        self.credential_mode = "authenticated"
        self.quota_snapshot: dict[str, Any] = {}
        self._branches = branches or {}
        self._list_error = list_error
        self.list_calls = 0

    def drain_transitions(self) -> list[Any]:
        return []

    def get_branch(self, owner: str, name: str, branch: str) -> dict[str, Any]:
        return {"name": branch, "head_sha": ORIGINAL_HEAD}

    def list_branches(self, owner: str, name: str, **_: object) -> list[dict[str, str]]:
        self.list_calls += 1
        if self._list_error is not None:
            raise self._list_error
        return self._branches.get(name, [])

    def compare_commits(self, owner: str, name: str, base: str, head: str) -> dict[str, Any]:
        return {"ahead": 3, "behind": 0, "last_activity": ACTIVITY}

    def close(self) -> None:
        pass


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


@pytest.fixture
def planned(session: Session) -> dict[str, Any]:
    """A completed branch-planning checkpoint with one selected fork branch."""
    root = Repository(
        github_id=1,
        owner="root",
        name="project",
        html_url="https://github.com/root/project",
        clone_url="https://github.com/root/project.git",
        default_branch="main",
        is_fork=False,
        archived=False,
        disabled=False,
    )
    fork = Repository(
        github_id=2,
        owner="someone",
        name="fork",
        html_url="https://github.com/someone/fork",
        clone_url="https://github.com/someone/fork.git",
        default_branch="main",
        is_fork=True,
        archived=False,
        disabled=False,
    )
    session.add_all([root, fork])
    session.flush()

    network = RepositoryNetwork(github_network_id="github:1", root_repository_id=root.id)
    session.add(network)
    session.flush()
    root.network_id = network.id
    fork.network_id = network.id

    analysis = AnalysisRun(
        requested_identifier="root/project",
        idempotency_key=f"idem-{uuid.uuid4()}",
        network_id=network.id,
        root_repository_id=root.id,
        sampling={
            "branch_cap": Settings().max_branches_per_fork,
            "branch_planner_version": BRANCH_PLANNER_VERSION,
        },
    )
    session.add(analysis)
    session.flush()

    session.add(
        RepositorySnapshot(analysis_id=analysis.id, repository_id=fork.id, shortlisted=True)
    )
    for repository in (root, fork):
        session.add(
            Branch(
                analysis_id=analysis.id,
                repository_id=repository.id,
                name="main",
                head_sha=ORIGINAL_HEAD,
                is_default=True,
                priority=0,
                decision="selected",
                selection_reason="default_branch",
                retrieval_time=datetime.now(UTC),
                planner_version=BRANCH_PLANNER_VERSION,
            )
        )
    session.add(
        StageCheckpoint(
            analysis_id=analysis.id,
            stage="branch_planning",
            status="completed",
            cursor={"considered": 2, "selected": 2},
            attempts=1,
        )
    )
    session.commit()
    return {"analysis": analysis, "root": root, "fork": fork}


def _pipeline(session: Session, router: ResumeRouter, **settings: Any) -> AnalysisPipeline:
    return AnalysisPipeline(
        session,
        settings=Settings(github_token=TOKEN, **settings),
        github=router,  # type: ignore[arg-type]
    )


def _unchanged_branches() -> dict[str, list[dict[str, str]]]:
    return {
        "project": [{"name": "main", "head_sha": ORIGINAL_HEAD}],
        "fork": [{"name": "main", "head_sha": ORIGINAL_HEAD}],
    }


def _branch_rows(session: Session, analysis: AnalysisRun, repo: Repository) -> list[Branch]:
    return list(
        session.scalars(
            select(Branch).where(
                Branch.analysis_id == analysis.id, Branch.repository_id == repo.id
            )
        )
    )


def test_unchanged_heads_reuse_the_existing_plan(
    session: Session, planned: dict[str, Any]
) -> None:
    analysis = planned["analysis"]
    router = ResumeRouter(branches=_unchanged_branches())

    _pipeline(session, router)._plan_branches(analysis)
    session.commit()

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    summary = stored.sampling["branch_plan_revalidation"]
    assert summary["reused"] == 2
    assert summary["replanned"] == 0
    assert summary["unvalidated"] == 0
    # The sealed plan is untouched: same head, same retrieval provenance.
    rows = _branch_rows(session, analysis, planned["fork"])
    assert len(rows) == 1
    assert rows[0].head_sha == ORIGINAL_HEAD


def test_moved_head_replans_only_that_repository(
    session: Session, planned: dict[str, Any]
) -> None:
    analysis = planned["analysis"]
    router = ResumeRouter(
        branches={
            "project": [{"name": "main", "head_sha": ORIGINAL_HEAD}],
            "fork": [{"name": "main", "head_sha": MOVED_HEAD}],
        }
    )

    _pipeline(session, router)._plan_branches(analysis)
    session.commit()

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    summary = stored.sampling["branch_plan_revalidation"]
    assert summary["reused"] == 1
    assert summary["replanned"] == 1
    # The cause is recorded so a re-planned repository is distinguishable.
    assert summary["replanned_repositories"][0]["cause"] == "head_moved"
    assert summary["replanned_repositories"][0]["repository_id"] == str(planned["fork"].id)

    # The moved repository now carries the current head; the untouched one does not.
    fork_rows = _branch_rows(session, analysis, planned["fork"])
    assert [row.head_sha for row in fork_rows] == [MOVED_HEAD]
    root_rows = _branch_rows(session, analysis, planned["root"])
    assert [row.head_sha for row in root_rows] == [ORIGINAL_HEAD]


def test_disappeared_branch_replans_with_its_own_cause(
    session: Session, planned: dict[str, Any]
) -> None:
    analysis = planned["analysis"]
    router = ResumeRouter(
        branches={
            "project": [{"name": "main", "head_sha": ORIGINAL_HEAD}],
            "fork": [{"name": "other", "head_sha": ORIGINAL_HEAD}],
        }
    )

    _pipeline(session, router)._plan_branches(analysis)
    session.commit()

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    causes = {
        item["cause"] for item in stored.sampling["branch_plan_revalidation"]["replanned_repositories"]
    }
    assert causes == {"branch_disappeared"}


def test_provider_unavailable_preserves_the_plan_and_says_so(
    session: Session, planned: dict[str, Any]
) -> None:
    analysis = planned["analysis"]
    router = ResumeRouter(
        list_error=GitHubError("repository_not_found", "gone", status_code=404)
    )

    _pipeline(session, router)._plan_branches(analysis)
    session.commit()

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    summary = stored.sampling["branch_plan_revalidation"]
    assert summary["unvalidated"] == 2
    assert summary["replanned"] == 0
    # Preserved rather than discarded...
    assert [row.head_sha for row in _branch_rows(session, analysis, planned["fork"])] == [
        ORIGINAL_HEAD
    ]
    # ...but never reported as confirmed current.
    assert any(
        warning.get("code") == "branch_plan_unvalidated" for warning in stored.warnings
    )


def test_provider_exhaustion_during_validation_propagates(
    session: Session, planned: dict[str, Any]
) -> None:
    """A spent quota is a run-level condition, not a per-repository verdict."""
    analysis = planned["analysis"]
    router = ResumeRouter(
        list_error=GitHubError(
            "github_rate_limited", "quota exhausted", status_code=503, details={"quota": {}}
        )
    )

    with pytest.raises(GitHubError) as caught:
        _pipeline(session, router)._plan_branches(analysis)

    assert caught.value.code == "github_rate_limited"


def test_changed_cap_invalidates_every_repository(
    session: Session, planned: dict[str, Any]
) -> None:
    """A different effective cap changes the selection inputs run-wide."""
    analysis = planned["analysis"]
    router = ResumeRouter(branches=_unchanged_branches())

    _pipeline(session, router, max_branches_per_fork=5)._plan_branches(analysis)
    session.commit()

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    summary = stored.sampling["branch_plan_revalidation"]
    assert summary["reused"] == 0
    assert summary["replanned"] == 2
    assert {item["cause"] for item in summary["replanned_repositories"]} == {
        "selection_inputs_changed"
    }
    assert stored.sampling["branch_cap"] == 5


def test_revalidation_does_not_rerun_a_first_pass(
    session: Session, planned: dict[str, Any]
) -> None:
    """Re-validation replaces the short-circuit, so it must not re-plan blindly."""
    analysis = planned["analysis"]
    router = ResumeRouter(branches=_unchanged_branches())

    _pipeline(session, router)._plan_branches(analysis)
    session.commit()

    # One listing per planned repository, and no planning probes beyond that.
    assert router.list_calls == 2
    checkpoint = session.scalar(
        select(StageCheckpoint).where(
            StageCheckpoint.analysis_id == analysis.id,
            StageCheckpoint.stage == "branch_planning",
        )
    )
    assert checkpoint is not None
    assert checkpoint.status == "completed"
    assert "revalidation" in checkpoint.cursor
