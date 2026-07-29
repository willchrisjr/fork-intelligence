from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from fork_intelligence.config import Settings
from fork_intelligence.db import Base
from fork_intelligence.domain.branch_planning import BRANCH_PLANNER_VERSION
from fork_intelligence.errors import GitHubError
from fork_intelligence.models import AnalysisRun, Branch, Repository, RepositorySnapshot
from fork_intelligence.services.pipeline import AnalysisPipeline

TOKEN = "ghp-operator-secret"  # noqa: S105 - inert fixture value.

ACTIVITY = "2026-07-20T00:00:00Z"


class PlanningRouter:
    """GitHub boundary scripted with branch listings and comparison probes."""

    def __init__(
        self,
        *,
        branches: dict[str, list[dict[str, str]]] | None = None,
        comparisons: dict[str, dict[str, Any]] | None = None,
        list_error: GitHubError | None = None,
        compare_error: GitHubError | None = None,
    ) -> None:
        self.credential_mode = "authenticated"
        self.quota_snapshot: dict[str, Any] = {}
        self._branches = branches or {}
        self._comparisons = comparisons or {}
        self._list_error = list_error
        self._compare_error = compare_error
        self.probe_calls = 0

    def drain_transitions(self) -> list[Any]:
        return []

    def get_repository(self, owner: str, name: str, **_: object) -> dict[str, Any]:
        raise AssertionError("planning stage should not resolve repositories")

    def get_branch(self, owner: str, name: str, branch: str) -> dict[str, Any]:
        return {"name": branch, "head_sha": f"{name}-{branch}-head"}

    def list_branches(
        self, owner: str, name: str, **_: object
    ) -> list[dict[str, str]]:
        if self._list_error is not None:
            raise self._list_error
        return self._branches.get(name, [])

    def compare_commits(
        self, owner: str, name: str, base: str, head: str
    ) -> dict[str, Any]:
        self.probe_calls += 1
        if self._compare_error is not None:
            raise self._compare_error
        return self._comparisons.get(head, {"ahead": 1, "behind": 0, "last_activity": ACTIVITY})

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
def analysis(session: Session) -> AnalysisRun:
    run = AnalysisRun(
        requested_identifier="root/project",
        idempotency_key=f"idem-{uuid.uuid4()}",
        configuration={},
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
        is_fork=github_id != 1,
        archived=False,
        disabled=False,
    )
    session.add(repo)
    session.flush()
    return repo


def _network_with_root(session: Session, analysis: AnalysisRun) -> Repository:
    from fork_intelligence.models import RepositoryNetwork

    root = _repository(session, 1, "root", "project")
    network = RepositoryNetwork(github_network_id="github:1", root_repository_id=root.id)
    session.add(network)
    session.flush()
    root.network_id = network.id
    analysis.network_id = network.id
    session.flush()
    return root


def _shortlisted_fork(
    session: Session, analysis: AnalysisRun, root: Repository, github_id: int, name: str
) -> Repository:
    fork = _repository(session, github_id, "someone", name)
    fork.network_id = root.network_id
    session.add(
        RepositorySnapshot(
            analysis_id=analysis.id, repository_id=fork.id, shortlisted=True
        )
    )
    session.flush()
    return fork


def _pipeline(session: Session, router: PlanningRouter, **settings: Any) -> AnalysisPipeline:
    return AnalysisPipeline(
        session,
        settings=Settings(github_token=TOKEN, **settings),
        github=router,  # type: ignore[arg-type]
    )


def _branches(session: Session, analysis: AnalysisRun, repo: Repository) -> list[Branch]:
    return list(
        session.scalars(
            select(Branch)
            .where(Branch.analysis_id == analysis.id, Branch.repository_id == repo.id)
            .order_by(Branch.priority)
        )
    )


def test_plan_persists_default_selection_and_coverage(
    session: Session, analysis: AnalysisRun
) -> None:
    root = _network_with_root(session, analysis)
    fork = _shortlisted_fork(session, analysis, root, 2, "fork")
    router = PlanningRouter(
        branches={
            "project": [{"name": "main", "head_sha": "root-main"}],
            "fork": [
                {"name": "main", "head_sha": "fork-main"},
                {"name": "feature", "head_sha": "fork-feature"},
            ],
        },
        comparisons={
            "feature": {"ahead": 12, "behind": 0, "last_activity": ACTIVITY},
        },
    )
    session.commit()

    _pipeline(session, router)._plan_branches(analysis)
    session.commit()

    fork_branches = _branches(session, analysis, fork)
    by_name = {branch.name: branch for branch in fork_branches}
    assert by_name["main"].decision == "selected"
    assert by_name["main"].is_default is True
    assert by_name["main"].priority == 0
    assert by_name["feature"].decision == "selected"
    assert by_name["feature"].selection_reason == "active_and_meaningfully_ahead"
    # All entries carry the new planner version, never WO-1's default-only one.
    assert all(branch.planner_version == BRANCH_PLANNER_VERSION for branch in fork_branches)

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert stored.sampling["branches_selected"] >= 3  # root main + fork main + feature
    assert stored.sampling["branch_planner_version"] == BRANCH_PLANNER_VERSION


def test_cap_excludes_surplus_branches_and_reports_it(
    session: Session, analysis: AnalysisRun
) -> None:
    root = _network_with_root(session, analysis)
    fork = _shortlisted_fork(session, analysis, root, 2, "fork")
    router = PlanningRouter(
        branches={
            "project": [{"name": "main", "head_sha": "root-main"}],
            "fork": [
                {"name": "main", "head_sha": "h0"},
                {"name": "a", "head_sha": "h1"},
                {"name": "b", "head_sha": "h2"},
                {"name": "c", "head_sha": "h3"},
            ],
        },
        comparisons={
            "a": {"ahead": 9, "behind": 0, "last_activity": ACTIVITY},
            "b": {"ahead": 6, "behind": 0, "last_activity": ACTIVITY},
            "c": {"ahead": 3, "behind": 0, "last_activity": ACTIVITY},
        },
    )
    session.commit()

    _pipeline(session, router, max_branches_per_fork=2)._plan_branches(analysis)
    session.commit()

    by_name = {b.name: b for b in _branches(session, analysis, fork)}
    assert by_name["main"].decision == "selected"
    assert by_name["a"].decision == "selected"
    assert by_name["b"].decision == "excluded"
    assert by_name["b"].selection_reason == "branch_cap_exceeded"
    assert by_name["c"].decision == "excluded"

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert stored.sampling["branches_excluded_by_cap"] == 2
    assert stored.sampling["branch_cap"] == 2


def test_probe_budget_leaves_surplus_candidates_unevaluated(
    session: Session, analysis: AnalysisRun
) -> None:
    root = _network_with_root(session, analysis)
    fork = _shortlisted_fork(session, analysis, root, 2, "fork")
    router = PlanningRouter(
        branches={
            "project": [{"name": "main", "head_sha": "root-main"}],
            "fork": [
                {"name": "main", "head_sha": "h0"},
                {"name": "probed", "head_sha": "h1"},
                {"name": "beyond", "head_sha": "h2"},
            ],
        }
    )
    session.commit()

    # Budget of one probe: the second non-default branch is left unevaluated.
    _pipeline(session, router, max_branch_probes=1)._plan_branches(analysis)
    session.commit()

    by_name = {b.name: b for b in _branches(session, analysis, fork)}
    assert by_name["beyond"].decision == "unevaluated"
    assert by_name["beyond"].selection_reason == "probe_budget_exhausted"
    # An unevaluated candidate is never given a definitive exclusion reason.
    assert by_name["beyond"].selection_reason != "branch_cap_exceeded"
    assert router.probe_calls == 1

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert stored.sampling["branches_unevaluated"] >= 1


def test_failed_probe_is_unevaluated_not_excluded(
    session: Session, analysis: AnalysisRun
) -> None:
    root = _network_with_root(session, analysis)
    fork = _shortlisted_fork(session, analysis, root, 2, "fork")
    router = PlanningRouter(
        branches={
            "project": [{"name": "main", "head_sha": "root-main"}],
            "fork": [
                {"name": "main", "head_sha": "h0"},
                {"name": "unreachable", "head_sha": "h1"},
            ],
        },
        compare_error=GitHubError("repository_not_found", "gone", status_code=404),
    )
    session.commit()

    _pipeline(session, router)._plan_branches(analysis)
    session.commit()

    entry = {b.name: b for b in _branches(session, analysis, fork)}["unreachable"]
    assert entry.decision == "unevaluated"
    assert entry.selection_reason == "relationship_probe_failed"


def test_enumeration_failure_still_plans_the_default_branch(
    session: Session, analysis: AnalysisRun
) -> None:
    root = _network_with_root(session, analysis)
    fork = _shortlisted_fork(session, analysis, root, 2, "fork")
    router = PlanningRouter(
        branches={"project": [{"name": "main", "head_sha": "root-main"}]},
        list_error=GitHubError("repository_not_found", "gone", status_code=404),
    )
    session.commit()

    _pipeline(session, router)._plan_branches(analysis)
    session.commit()

    fork_branches = _branches(session, analysis, fork)
    # The default is resolved via get_branch and planned alone (AC-RA-RBP-001.5).
    assert len(fork_branches) == 1
    assert fork_branches[0].is_default is True
    assert fork_branches[0].decision == "selected"


def test_provider_exhaustion_during_planning_propagates(
    session: Session, analysis: AnalysisRun
) -> None:
    root = _network_with_root(session, analysis)
    _shortlisted_fork(session, analysis, root, 2, "fork")
    router = PlanningRouter(
        list_error=GitHubError(
            "github_rate_limited", "quota exhausted", status_code=503, details={"quota": {}}
        )
    )
    session.commit()

    with pytest.raises(GitHubError) as caught:
        _pipeline(session, router)._plan_branches(analysis)

    assert caught.value.code == "github_rate_limited"


def test_plan_is_idempotent_across_repeated_runs(
    session: Session, analysis: AnalysisRun
) -> None:
    root = _network_with_root(session, analysis)
    fork = _shortlisted_fork(session, analysis, root, 2, "fork")
    branches = {
        "project": [{"name": "main", "head_sha": "root-main"}],
        "fork": [
            {"name": "main", "head_sha": "h0"},
            {"name": "x", "head_sha": "h1"},
            {"name": "y", "head_sha": "h2"},
        ],
    }
    comparisons = {
        "x": {"ahead": 5, "behind": 0, "last_activity": ACTIVITY},
        "y": {"ahead": 5, "behind": 0, "last_activity": ACTIVITY},
    }
    session.commit()

    _pipeline(session, PlanningRouter(branches=branches, comparisons=comparisons))._plan_branches(
        analysis
    )
    session.commit()
    first = [(b.name, b.decision, b.priority) for b in _branches(session, analysis, fork)]

    # Re-running the stage over the same inputs must not create duplicates or
    # change decisions (AC-RA-RBP-003.1). The stage checkpoint would normally
    # short-circuit; force a re-run to prove the recorder is stable too.
    pipeline = _pipeline(session, PlanningRouter(branches=branches, comparisons=comparisons))
    pipeline._stage_complete = lambda *_: False  # type: ignore[method-assign]
    pipeline._plan_branches(analysis)
    session.commit()
    second = [(b.name, b.decision, b.priority) for b in _branches(session, analysis, fork)]

    assert first == second
