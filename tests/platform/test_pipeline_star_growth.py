from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from fork_intelligence.config import Settings
from fork_intelligence.db import Base
from fork_intelligence.errors import GitHubError
from fork_intelligence.models import (
    AnalysisRun,
    EvidenceItem,
    Repository,
    RepositoryNetwork,
    RepositorySnapshot,
)
from fork_intelligence.services.pipeline import AnalysisPipeline

TOKEN = "ghp-operator-secret"  # noqa: S105 - inert fixture value.


class StarGrowthRouter:
    """GitHub boundary scripted with identity-free star aggregates only."""

    def __init__(
        self,
        *,
        counts: dict[str, int] | None = None,
        histories: dict[str, list[dict[str, int]]] | None = None,
        errors: dict[str, GitHubError] | None = None,
    ) -> None:
        self.credential_mode = "anonymous"
        self.quota_snapshot: dict[str, Any] = {}
        self._counts = counts or {}
        self._histories = histories or {}
        self._errors = errors or {}
        self.paths: list[str] = []

    def drain_transitions(self) -> list[Any]:
        return []

    def get_stargazer_count(self, owner: str, name: str) -> dict[str, int]:
        locator = f"{owner}/{name}"
        self.paths.append(f"/repos/{locator}/stargazers/count")
        if locator in self._errors:
            raise self._errors[locator]
        return {"count": self._counts[locator]}

    def get_stargazer_history(
        self, owner: str, name: str, *, per_page: int = 12
    ) -> list[dict[str, int]]:
        locator = f"{owner}/{name}"
        self.paths.append(f"/repos/{locator}/stargazers/history?per_page={per_page}")
        if locator in self._errors:
            raise self._errors[locator]
        return list(self._histories[locator])

    def close(self) -> None:
        pass


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


def _seed(
    session: Session,
    *,
    forks: list[tuple[int, str, int]],
) -> AnalysisRun:
    network = RepositoryNetwork()
    session.add(network)
    session.flush()
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
        network_id=network.id,
    )
    session.add(root)
    session.flush()
    network.root_repository_id = root.id
    analysis = AnalysisRun(
        requested_identifier="root/project",
        idempotency_key=f"idem-{uuid.uuid4()}",
        configuration={"max_shortlist": 1},
        network_id=network.id,
        root_repository_id=root.id,
    )
    session.add(analysis)
    session.flush()
    session.add(
        RepositorySnapshot(
            analysis_id=analysis.id,
            repository_id=root.id,
            raw_metadata={"stars": 9},
        )
    )
    for github_id, full_name, stars in forks:
        owner, name = full_name.split("/", 1)
        fork = Repository(
            github_id=github_id,
            owner=owner,
            name=name,
            html_url=f"https://github.com/{full_name}",
            clone_url=f"https://github.com/{full_name}.git",
            default_branch="main",
            is_fork=True,
            archived=False,
            disabled=False,
            network_id=network.id,
        )
        session.add(fork)
        session.flush()
        session.add(
            RepositorySnapshot(
                analysis_id=analysis.id,
                repository_id=fork.id,
                raw_metadata={"stars": stars, "pushed_at": "2026-09-01T00:00:00Z", "forks": 1},
            )
        )
    session.commit()
    return analysis


def _pipeline(session: Session, router: StarGrowthRouter) -> AnalysisPipeline:
    return AnalysisPipeline(
        session,
        settings=Settings(github_token=TOKEN, max_shortlist=1),
        github=router,  # type: ignore[arg-type]
    )


def test_shortlisted_fork_stores_count_endpoint_not_history_sum(session: Session) -> None:
    analysis = _seed(
        session,
        forks=[(2, "lab/hot", 80), (3, "lab/cold", 2)],
    )
    history = [
        {"week": 12, "total": 350},
        {"week": 11, "total": 10},
        {"week": 10, "total": 10},
        {"week": 9, "total": 10},
    ]
    router = StarGrowthRouter(
        counts={"lab/hot": 1284, "lab/cold": 2},
        histories={"lab/hot": history, "lab/cold": history},
    )

    _pipeline(session, router)._shortlist(analysis)
    session.commit()

    hot = session.scalar(select(Repository).where(Repository.name == "hot"))
    cold = session.scalar(select(Repository).where(Repository.name == "cold"))
    assert hot is not None and cold is not None
    hot_snap = session.scalar(
        select(RepositorySnapshot).where(RepositorySnapshot.repository_id == hot.id)
    )
    cold_snap = session.scalar(
        select(RepositorySnapshot).where(RepositorySnapshot.repository_id == cold.id)
    )
    assert hot_snap is not None and cold_snap is not None
    growth = hot_snap.metrics["star_growth"]
    assert growth["count"] == 1284
    assert growth["count"] != sum(week["total"] for week in history)
    assert growth["created_last_4w"] == 380
    assert cold_snap.shortlisted is False
    assert "star_growth" not in cold_snap.metrics
    assert router.paths == [
        "/repos/lab/hot/stargazers/count",
        "/repos/lab/hot/stargazers/history?per_page=12",
    ]
    assert all("stargazers" in path and not path.endswith("/stargazers") for path in router.paths)

    evidence = session.scalars(
        select(EvidenceItem).where(EvidenceItem.repository_id == hot.id)
    ).all()
    assert len(evidence) == 1
    assert evidence[0].source == "github"
    assert evidence[0].payload["title"] == "Privacy-safe star growth"
    assert evidence[0].provenance["api_version"] == "2026-03-10"
    assert evidence[0].provenance["endpoints"] == ["stargazers/count", "stargazers/history"]


def test_star_growth_failure_is_missing_data_not_a_failed_run(session: Session) -> None:
    analysis = _seed(session, forks=[(2, "lab/hot", 80)])
    router = StarGrowthRouter(
        errors={
            "lab/hot": GitHubError("repository_not_found", "gone", status_code=404),
        }
    )

    _pipeline(session, router)._shortlist(analysis)
    session.commit()

    snapshot = session.scalar(
        select(RepositorySnapshot).where(RepositorySnapshot.shortlisted.is_(True))
    )
    assert snapshot is not None
    assert snapshot.metrics["missing_data"] == [
        "Privacy-safe star history was unavailable from GitHub"
    ]
    assert "star_growth" not in snapshot.metrics
    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert stored.status != "failed"


def test_provider_exhaustion_during_star_growth_still_stops_the_run(session: Session) -> None:
    analysis = _seed(session, forks=[(2, "lab/hot", 80)])
    router = StarGrowthRouter(
        errors={
            "lab/hot": GitHubError(
                "github_rate_limited",
                "quota",
                status_code=503,
                details={"quota": {"remaining": 0}},
            )
        }
    )

    with pytest.raises(GitHubError) as caught:
        _pipeline(session, router)._shortlist(analysis)

    assert caught.value.code == "github_rate_limited"
