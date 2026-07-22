from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from fork_intelligence.adapters.credential_router import (
    COVERAGE_LIMITATION,
    CredentialModeTransition,
)
from fork_intelligence.adapters.github import GitHubClient, GitHubPage
from fork_intelligence.config import Settings
from fork_intelligence.db import Base
from fork_intelligence.errors import GitHubError
from fork_intelligence.models import (
    AnalysisRun,
    ProgressEvent,
    Repository,
    RepositorySnapshot,
)
from fork_intelligence.services.pipeline import AnalysisPipeline

TOKEN = "ghp-operator-secret"  # noqa: S105 - inert fixture value.

QUOTA = {"limit": 60, "remaining": 0, "reset": 123, "resource": "core"}


def _raw_repository(repository_id: int, full_name: str) -> dict[str, Any]:
    owner, name = full_name.split("/", 1)
    return {
        "id": repository_id,
        "name": name,
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "clone_url": f"https://github.com/{full_name}.git",
        "owner": {"login": owner},
        "default_branch": "main",
        "fork": False,
        "archived": False,
        "disabled": False,
    }


def _normalized(repository_id: int, full_name: str) -> dict[str, Any]:
    return GitHubClient.normalize_repository(_raw_repository(repository_id, full_name))


class FakeRouter:
    """Stands in for GitHubCredentialRouter with scripted access behavior."""

    def __init__(
        self,
        *,
        mode: str = "authenticated",
        transitions: list[CredentialModeTransition] | None = None,
        forks_error: GitHubError | None = None,
    ) -> None:
        self.credential_mode = mode
        self.quota_snapshot = {**QUOTA, "credential_mode": mode}
        self._transitions = transitions or []
        self._forks_error = forks_error
        self.closed = False

    def drain_transitions(self) -> list[CredentialModeTransition]:
        pending = self._transitions
        self._transitions = []
        return pending

    def get_repository(self, owner: str, name: str, **_: object) -> dict[str, Any]:
        return _normalized(1, f"{owner}/{name}")

    def get_branch(self, owner: str, name: str, branch: str) -> dict[str, Any]:
        return {"name": branch, "head_sha": "a" * 40}

    def iter_forks(self, owner: str, name: str, **_: object) -> Iterator[GitHubPage]:
        if self._forks_error is not None:
            raise self._forks_error
        return iter(())

    def close(self) -> None:
        self.closed = True


def _fallback_transition() -> CredentialModeTransition:
    return CredentialModeTransition(
        from_mode="authenticated",
        to_mode="anonymous",
        reason="operator_credential_quota_exhausted",
        coverage_limitation=COVERAGE_LIMITATION,
        occurred_at="2026-07-22T00:00:00+00:00",
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
    run = AnalysisRun(
        requested_identifier="root/project",
        idempotency_key=f"idem-{uuid.uuid4()}",
        configuration={"analysis_depth": "metadata"},
    )
    session.add(run)
    session.commit()
    return run


def _pipeline(session: Session, router: FakeRouter) -> AnalysisPipeline:
    return AnalysisPipeline(
        session,
        settings=Settings(github_token=TOKEN),
        github=router,  # type: ignore[arg-type]
    )


def test_effective_mode_and_quota_are_visible_during_collection(
    session: Session, analysis: AnalysisRun
) -> None:
    router = FakeRouter(mode="authenticated")
    _pipeline(session, router)._resolve(analysis)
    session.commit()

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert stored.credential_mode == "authenticated"
    assert stored.quota_snapshot["remaining"] == 0
    assert stored.quota_snapshot["credential_mode"] == "authenticated"


def test_router_fallback_is_persisted_as_a_mode_transition(
    session: Session, analysis: AnalysisRun
) -> None:
    router = FakeRouter(mode="anonymous", transitions=[_fallback_transition()])
    _pipeline(session, router)._resolve(analysis)
    session.commit()

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert stored.credential_mode == "anonymous"
    assert len(stored.credential_mode_transitions) == 1
    transition = stored.credential_mode_transitions[0]
    assert transition["from_mode"] == "authenticated"
    assert transition["to_mode"] == "anonymous"
    assert transition["reason"] == "operator_credential_quota_exhausted"
    assert transition["coverage_limitation"] == COVERAGE_LIMITATION


def test_exhausting_every_access_mode_preserves_partial_results(
    session: Session, analysis: AnalysisRun
) -> None:
    router = FakeRouter(
        mode="anonymous",
        transitions=[_fallback_transition()],
        forks_error=GitHubError(
            "github_rate_limited",
            "GitHub denied the request or its API quota is exhausted",
            status_code=503,
            details={"quota": QUOTA},
        ),
    )

    _pipeline(session, router).run(analysis.id)

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    # AC-RA-AGA-002.4: the run degrades to partial rather than failing, and the
    # evidence committed before access ran out survives the rollback.
    assert stored.status == "partial"
    assert stored.stage == "waiting_for_quota"
    assert stored.credential_mode == "anonymous"
    assert session.scalar(select(Repository).where(Repository.owner == "root")) is not None

    warning = stored.warnings[-1]
    assert warning["code"] == "provider_access_exhausted"
    assert warning["credential_mode"] == "anonymous"
    assert stored.error is not None
    assert stored.error["credential_mode"] == "anonymous"


def test_rejected_credential_leaves_a_resumable_provider_condition(
    session: Session, analysis: AnalysisRun
) -> None:
    router = FakeRouter(
        mode="anonymous",
        forks_error=GitHubError(
            "github_unauthorized",
            "GitHub denied the request",
            status_code=503,
            details={"quota": QUOTA},
        ),
    )

    _pipeline(session, router).run(analysis.id)

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert stored.status == "partial"
    # A rejected credential is not cured by waiting, so it must not be filed
    # under the quota-reset stage that the resume path advertises.
    assert stored.stage == "waiting_for_provider"
    assert "provider access is restored" in stored.warnings[-1]["message"]


def test_unrelated_github_failures_still_fail_the_analysis(
    session: Session, analysis: AnalysisRun
) -> None:
    router = FakeRouter(
        forks_error=GitHubError("repository_not_found", "gone", status_code=404),
    )

    with pytest.raises(GitHubError):
        _pipeline(session, router).run(analysis.id)

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert stored.status == "failed"


def test_fallback_survives_an_unrelated_failure(session: Session, analysis: AnalysisRun) -> None:
    router = FakeRouter(
        mode="anonymous",
        transitions=[_fallback_transition()],
        forks_error=GitHubError("repository_not_found", "gone", status_code=404),
    )

    with pytest.raises(GitHubError):
        _pipeline(session, router).run(analysis.id)

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert stored.status == "failed"
    # The run failed for an unrelated reason, but it still ran under degraded
    # access and that has to remain on the record.
    assert stored.credential_mode == "anonymous"
    assert len(stored.credential_mode_transitions) == 1


def test_resumed_run_reconciles_a_recovered_credential(
    session: Session, analysis: AnalysisRun
) -> None:
    # A previous attempt fell back and persisted anonymous.
    analysis.credential_mode = "anonymous"
    session.commit()

    # The resumed attempt builds a fresh router whose credential works again.
    router = FakeRouter(mode="authenticated")
    _pipeline(session, router)._resolve(analysis)
    session.commit()

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert stored.credential_mode == "authenticated"
    assert stored.credential_mode_transitions[-1]["reason"] == (
        "provider_access_revalidated_on_resume"
    )


class _StubStore:
    """Stands in for BareNetworkStore so structural tests stay off the network."""

    def __init__(self, *_: object, **__: object) -> None:
        pass

    def fetch_branch(self, *_: object, **__: object) -> str:
        return "ref"

    def compare(self, *_: object, **__: object) -> Any:
        raise AssertionError("comparison should not be reached in these tests")


def _shortlisted_fork(session: Session, analysis: AnalysisRun) -> Repository:
    """Give the structural stage one shortlisted fork to work through."""
    fork = Repository(
        github_id=99,
        owner="someone",
        name="fork",
        html_url="https://github.com/someone/fork",
        clone_url="https://github.com/someone/fork.git",
        default_branch="main",
        is_fork=True,
        archived=False,
        disabled=False,
        network_id=analysis.network_id,
    )
    session.add(fork)
    session.flush()
    session.add(
        RepositorySnapshot(
            analysis_id=analysis.id,
            repository_id=fork.id,
            shortlisted=True,
        )
    )
    session.commit()
    return fork


def _structural_pipeline(
    session: Session,
    analysis: AnalysisRun,
    monkeypatch: pytest.MonkeyPatch,
    router: FakeRouter,
) -> AnalysisPipeline:
    monkeypatch.setattr("fork_intelligence.services.pipeline.BareNetworkStore", _StubStore)
    pipeline = _pipeline(session, router)
    pipeline._resolve(analysis)
    session.commit()
    _shortlisted_fork(session, analysis)
    return pipeline


class _FailingForkBranch(FakeRouter):
    """Succeeds for the root repository, fails for every fork."""

    error: GitHubError

    def get_branch(self, owner: str, name: str, branch: str) -> dict[str, Any]:
        if owner == "root":
            return {"name": branch, "head_sha": "a" * 40}
        raise self.error


def test_provider_exhaustion_during_structural_analysis_is_not_swallowed(
    session: Session, analysis: AnalysisRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider-wide outage must not be filed as a per-repository warning."""
    router = _FailingForkBranch(mode="anonymous")
    router.error = GitHubError(
        "github_rate_limited", "quota exhausted", status_code=503, details={"quota": QUOTA}
    )
    pipeline = _structural_pipeline(session, analysis, monkeypatch, router)

    with pytest.raises(GitHubError) as caught:
        pipeline._structural(analysis)

    assert caught.value.code == "github_rate_limited"
    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    # It must not have been downgraded into a survivable per-repository note.
    assert all(warning.get("code") != "github_rate_limited" for warning in stored.warnings)


def test_repository_specific_failures_remain_per_repository_warnings(
    session: Session, analysis: AnalysisRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    router = _FailingForkBranch()
    router.error = GitHubError("repository_not_found", "gone", status_code=404)
    pipeline = _structural_pipeline(session, analysis, monkeypatch, router)

    # Does not raise: one unavailable repository is survivable.
    pipeline._structural(analysis)

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert any(warning.get("code") == "repository_not_found" for warning in stored.warnings)


def test_operator_credential_never_reaches_persisted_state(
    session: Session, analysis: AnalysisRun
) -> None:
    router = FakeRouter(mode="anonymous", transitions=[_fallback_transition()])
    _pipeline(session, router).run(analysis.id)

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    events = session.scalars(
        select(ProgressEvent).where(ProgressEvent.analysis_id == analysis.id)
    ).all()

    # AC-RA-AGA-001.3: no analysis record, event, warning, or quota disclosure
    # may carry credential material.
    surfaces = [
        str(stored.credential_mode_transitions),
        str(stored.quota_snapshot),
        str(stored.warnings),
        str(stored.error),
        str(stored.configuration),
        str(stored.sampling),
        *[str(event.payload) for event in events],
    ]
    assert TOKEN not in "".join(surfaces)
