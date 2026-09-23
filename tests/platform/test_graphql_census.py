"""Census persistence for the GraphQL fork accelerator."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from fork_intelligence.adapters.credential_router import CredentialModeTransition
from fork_intelligence.adapters.github import GitHubClient, GitHubPage
from fork_intelligence.config import Settings
from fork_intelligence.db import Base
from fork_intelligence.models import (
    AnalysisRun,
    ProgressEvent,
    Repository,
    RepositorySnapshot,
    StageCheckpoint,
)
from fork_intelligence.services.pipeline import AnalysisPipeline

TOKEN = "ghp-operator-secret"  # noqa: S105 - inert fixture value.


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
    }


def _normalized(repository_id: int, full_name: str) -> dict[str, Any]:
    return GitHubClient.normalize_repository(_raw_repository(repository_id, full_name))


def _graphql_fork(repository_id: int, full_name: str) -> dict[str, Any]:
    item = _normalized(repository_id, full_name)
    item["is_fork"] = True
    item["field_provenance"] = {
        "github_id": "github_graphql",
        "clone_url": "derived_canonical_https",
        "html_url": "derived_canonical_https",
        "stars": "github_graphql",
        "source": "not_supplied",
    }
    return item


class _CensusRouter:
    def __init__(self, pages: list[GitHubPage] | None = None) -> None:
        self.credential_mode = "authenticated"
        self.quota_snapshot = {"limit": 5000, "remaining": 10, "resource": "graphql"}
        self.graphql_points_spent = 2
        self.graphql_degradations: list[str] = []
        self.graphql_partial_errors: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self._pages = pages
        self.closed = False

    def drain_transitions(self) -> list[CredentialModeTransition]:
        return []

    def get_repository(self, owner: str, name: str, **_: object) -> dict[str, Any]:
        return _normalized(1, f"{owner}/{name}")

    def iter_forks(self, owner: str, name: str, **kwargs: object) -> Iterator[GitHubPage]:
        self.calls.append({"owner": owner, "name": name, **kwargs})
        if self._pages is not None:
            return iter(self._pages)
        if owner == "root":
            return iter(
                [
                    GitHubPage(
                        items=[
                            _graphql_fork(11, "fork/one"),
                            _graphql_fork(11, "fork/one"),
                        ],
                        page=1,
                        has_next=False,
                        etag=None,
                        quota={"limit": 5000, "remaining": 9, "resource": "graphql"},
                        cursor="Y3Vyc29yMQ",
                        transport="github_graphql",
                        graphql_cost=1,
                        inaccessible_count=1,
                    )
                ]
            )
        return iter(())

    def close(self) -> None:
        self.closed = True


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


def _pipeline(session: Session, router: _CensusRouter) -> AnalysisPipeline:
    return AnalysisPipeline(
        session,
        settings=Settings(github_token=TOKEN),
        github=router,  # type: ignore[arg-type]
    )


def test_graphql_fork_snapshots_record_field_provenance_and_sampling(
    session: Session, analysis: AnalysisRun
) -> None:
    router = _CensusRouter()
    pipeline = _pipeline(session, router)
    pipeline._resolve(analysis)
    pipeline._census(analysis)
    session.commit()

    fork = session.scalar(select(Repository).where(Repository.github_id == 11))
    assert fork is not None
    assert fork.metadata_json.get("field_provenance") is None
    assert fork.clone_url == "https://github.com/fork/one.git"
    snapshot = session.scalar(
        select(RepositorySnapshot).where(RepositorySnapshot.repository_id == fork.id)
    )
    assert snapshot is not None
    assert snapshot.provenance["source"] == "github_graphql"
    assert snapshot.provenance["fields"]["clone_url"] == "derived_canonical_https"
    assert snapshot.provenance["fields"]["stars"] == "github_graphql"
    assert snapshot.provenance["fields"]["source"] == "not_supplied"
    assert TOKEN not in str(snapshot.provenance)

    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert stored.sampling["graphql_pages"] == 1
    assert stored.sampling["graphql_cost"] == 2
    assert stored.sampling["graphql_inaccessible_forks"] == 1
    assert stored.sampling["accessible_forks"] == 1
    assert any(warning["code"] == "graphql_inaccessible_forks" for warning in stored.warnings)

    event = session.scalar(
        select(ProgressEvent).where(ProgressEvent.event_type == "census.page_persisted")
    )
    assert event is not None
    assert event.payload["transport"] == "github_graphql"
    assert event.payload["inaccessible_count"] == 1
    assert "graphql_cursor" not in event.payload
    assert TOKEN not in str(event.payload)


def test_census_resumes_the_interrupted_graphql_cursor(
    session: Session, analysis: AnalysisRun
) -> None:
    pipeline = _pipeline(session, _CensusRouter())
    pipeline._resolve(analysis)
    pipeline._census(analysis)
    session.commit()

    checkpoint = session.scalar(
        select(StageCheckpoint).where(
            StageCheckpoint.analysis_id == analysis.id,
            StageCheckpoint.stage == "census",
        )
    )
    assert checkpoint is not None
    checkpoint.status = "running"
    checkpoint.cursor = {
        "parent_github_id": 1,
        "page": 1,
        "has_next": True,
        "transport": "github_graphql",
        "graphql_cursor": "Y3Vyc29yMQ",
        "note": f"do-not-persist-{TOKEN}",
    }
    session.commit()

    resumed = _CensusRouter(pages=[])
    _pipeline(session, resumed)._census(analysis)

    root_call = next(call for call in resumed.calls if call["owner"] == "root")
    assert root_call["start_page"] == 2
    assert root_call["graphql_cursor"] == "Y3Vyc29yMQ"
    assert TOKEN not in str(resumed.calls)
