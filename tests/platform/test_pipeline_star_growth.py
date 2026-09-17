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
    root_full_name: str = "root/project",
    root_is_fork: bool = False,
    link_forks_to_root: bool = False,
    max_shortlist: int = 1,
    fork_relationships: dict[str, dict[str, Any]] | None = None,
) -> AnalysisRun:
    network = RepositoryNetwork()
    session.add(network)
    session.flush()
    root_owner, root_name = root_full_name.split("/", 1)
    root = Repository(
        github_id=1,
        owner=root_owner,
        name=root_name,
        html_url=f"https://github.com/{root_full_name}",
        clone_url=f"https://github.com/{root_full_name}.git",
        default_branch="main",
        is_fork=root_is_fork,
        archived=False,
        disabled=False,
        network_id=network.id,
    )
    session.add(root)
    session.flush()
    network.root_repository_id = root.id
    analysis = AnalysisRun(
        requested_identifier=root_full_name,
        idempotency_key=f"idem-{uuid.uuid4()}",
        configuration={"max_shortlist": max_shortlist},
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
        if link_forks_to_root:
            fork.parent_repository_id = root.id
            fork.source_repository_id = root.id
        metadata = dict((fork_relationships or {}).get(full_name) or {})
        if metadata:
            fork.metadata_json = metadata
        session.add(
            RepositorySnapshot(
                analysis_id=analysis.id,
                repository_id=fork.id,
                raw_metadata={
                    "stars": stars,
                    "pushed_at": "2026-09-01T00:00:00Z",
                    "forks": 1,
                    **metadata,
                },
            )
        )
    session.commit()
    return analysis


def _pipeline(
    session: Session, router: StarGrowthRouter, *, max_shortlist: int = 1
) -> AnalysisPipeline:
    return AnalysisPipeline(
        session,
        settings=Settings(github_token=TOKEN, max_shortlist=max_shortlist),
        github=router,  # type: ignore[arg-type]
    )


def _weeks(*totals: int) -> list[dict[str, int]]:
    return [{"week": index + 1, "total": total} for index, total in enumerate(totals)]


BARRIER_WEEKS = _weeks(12, 30, 21, 24, 7, 35, 19, 34, 31, 44, 17, 22)
DESKFLOW_WEEKS = _weeks(127, 195, 198, 174, 172, 172, 166, 171, 171, 230, 154, 145)
IDENTITY_KEYS = ("login", "avatar_url", "user", "stargazers")


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
    assert "vs_upstream" not in growth
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


def test_true_fork_with_parent_adds_vs_upstream_and_at_most_two_extra_calls(
    session: Session,
) -> None:
    analysis = _seed(
        session,
        forks=[(2, "debauchee/barrier", 80), (3, "lab/cold", 2)],
        root_full_name="deskflow/deskflow",
        link_forks_to_root=True,
    )
    router = StarGrowthRouter(
        counts={"debauchee/barrier": 30879, "lab/cold": 2, "deskflow/deskflow": 28912},
        histories={
            "debauchee/barrier": BARRIER_WEEKS,
            "lab/cold": BARRIER_WEEKS,
            "deskflow/deskflow": DESKFLOW_WEEKS,
        },
    )

    _pipeline(session, router)._shortlist(analysis)
    session.commit()

    barrier = session.scalar(select(Repository).where(Repository.name == "barrier"))
    assert barrier is not None
    snapshot = session.scalar(
        select(RepositorySnapshot).where(RepositorySnapshot.repository_id == barrier.id)
    )
    assert snapshot is not None
    growth = snapshot.metrics["star_growth"]
    assert growth["count"] == 30879
    assert growth["created_last_4w"] == 87
    assert growth["created_last_12w"] == 296
    assert growth["vs_upstream"] == {
        "full_name": "deskflow/deskflow",
        "created_last_4w": 694,
        "created_last_12w": 2075,
        "ratio_4w": 0.13,
        "ratio_12w": 0.14,
    }
    assert "count" not in growth["vs_upstream"]
    assert "weekly_created" not in growth["vs_upstream"]
    assert all(key not in growth["vs_upstream"] for key in IDENTITY_KEYS)
    assert all(key not in growth for key in IDENTITY_KEYS)
    assert router.paths == [
        "/repos/debauchee/barrier/stargazers/count",
        "/repos/debauchee/barrier/stargazers/history?per_page=12",
        "/repos/deskflow/deskflow/stargazers/count",
        "/repos/deskflow/deskflow/stargazers/history?per_page=12",
    ]
    assert all("stargazers" in path and not path.endswith("/stargazers") for path in router.paths)

    evidence = session.scalars(
        select(EvidenceItem).where(EvidenceItem.repository_id == barrier.id)
    ).all()
    assert len(evidence) == 1
    assert evidence[0].payload["vs_upstream"]["full_name"] == "deskflow/deskflow"
    assert all(key not in evidence[0].payload for key in IDENTITY_KEYS)


def test_non_fork_star_growth_does_not_fetch_or_store_vs_upstream(session: Session) -> None:
    analysis = _seed(session, forks=[], root_is_fork=False)
    router = StarGrowthRouter(
        counts={"root/project": 1284},
        histories={"root/project": BARRIER_WEEKS},
    )

    _pipeline(session, router)._shortlist(analysis)
    session.commit()

    root = session.scalar(select(Repository).where(Repository.name == "project"))
    assert root is not None
    snapshot = session.scalar(
        select(RepositorySnapshot).where(RepositorySnapshot.repository_id == root.id)
    )
    assert snapshot is not None
    assert snapshot.shortlisted is True
    assert "vs_upstream" not in snapshot.metrics["star_growth"]
    assert router.paths == [
        "/repos/root/project/stargazers/count",
        "/repos/root/project/stargazers/history?per_page=12",
    ]


def test_all_zero_fork_series_skips_vs_upstream_and_parent_calls(session: Session) -> None:
    analysis = _seed(
        session,
        forks=[(2, "miguelgrinberg/flask", 80)],
        root_full_name="pallets/flask",
        link_forks_to_root=True,
    )
    router = StarGrowthRouter(
        counts={"miguelgrinberg/flask": 47, "pallets/flask": 74746},
        histories={
            "miguelgrinberg/flask": _weeks(*([0] * 12)),
            "pallets/flask": DESKFLOW_WEEKS,
        },
    )

    _pipeline(session, router)._shortlist(analysis)
    session.commit()

    fork = session.scalar(
        select(Repository).where(
            Repository.owner == "miguelgrinberg", Repository.name == "flask"
        )
    )
    assert fork is not None
    snapshot = session.scalar(
        select(RepositorySnapshot).where(RepositorySnapshot.repository_id == fork.id)
    )
    assert snapshot is not None
    growth = snapshot.metrics["star_growth"]
    assert growth["created_last_12w"] == 0
    assert "vs_upstream" not in growth
    assert router.paths == [
        "/repos/miguelgrinberg/flask/stargazers/count",
        "/repos/miguelgrinberg/flask/stargazers/history?per_page=12",
    ]


def test_parent_aggregates_are_cached_across_shortlisted_forks(session: Session) -> None:
    analysis = _seed(
        session,
        forks=[(2, "lab/hot", 80), (3, "lab/warmer", 70)],
        root_full_name="deskflow/deskflow",
        link_forks_to_root=True,
        max_shortlist=2,
    )
    router = StarGrowthRouter(
        counts={"lab/hot": 100, "lab/warmer": 90, "deskflow/deskflow": 28912},
        histories={
            "lab/hot": BARRIER_WEEKS,
            "lab/warmer": BARRIER_WEEKS,
            "deskflow/deskflow": DESKFLOW_WEEKS,
        },
    )

    _pipeline(session, router, max_shortlist=2)._shortlist(analysis)
    session.commit()

    parent_paths = [path for path in router.paths if path.startswith("/repos/deskflow/deskflow/")]
    assert parent_paths == [
        "/repos/deskflow/deskflow/stargazers/count",
        "/repos/deskflow/deskflow/stargazers/history?per_page=12",
    ]
    assert router.paths.count("/repos/lab/hot/stargazers/count") == 1
    assert router.paths.count("/repos/lab/warmer/stargazers/count") == 1


def test_metadata_parent_is_used_when_fk_is_absent(session: Session) -> None:
    analysis = _seed(
        session,
        forks=[(2, "debauchee/barrier", 80)],
        fork_relationships={
            "debauchee/barrier": {
                "parent": {
                    "github_id": 99,
                    "full_name": "deskflow/deskflow",
                    "html_url": "https://github.com/deskflow/deskflow",
                    "clone_url": "https://github.com/deskflow/deskflow.git",
                    "default_branch": "main",
                    "login": "must-not-be-copied",
                }
            }
        },
    )
    router = StarGrowthRouter(
        counts={"debauchee/barrier": 30879, "deskflow/deskflow": 28912},
        histories={"debauchee/barrier": BARRIER_WEEKS, "deskflow/deskflow": DESKFLOW_WEEKS},
    )

    _pipeline(session, router)._shortlist(analysis)
    session.commit()

    fork = session.scalar(select(Repository).where(Repository.name == "barrier"))
    assert fork is not None
    snapshot = session.scalar(
        select(RepositorySnapshot).where(RepositorySnapshot.repository_id == fork.id)
    )
    assert snapshot is not None
    assert snapshot.metrics["star_growth"]["vs_upstream"]["full_name"] == "deskflow/deskflow"
    assert "login" not in snapshot.metrics["star_growth"]["vs_upstream"]
    assert "/repos/deskflow/deskflow/stargazers/count" in router.paths


def test_parent_star_growth_failure_omits_line_and_keeps_fork_panel(session: Session) -> None:
    analysis = _seed(
        session,
        forks=[(2, "debauchee/barrier", 80)],
        root_full_name="deskflow/deskflow",
        link_forks_to_root=True,
    )
    router = StarGrowthRouter(
        counts={"debauchee/barrier": 30879},
        histories={"debauchee/barrier": BARRIER_WEEKS},
        errors={"deskflow/deskflow": GitHubError("repository_not_found", "gone", status_code=404)},
    )

    _pipeline(session, router)._shortlist(analysis)
    session.commit()

    snapshot = session.scalar(
        select(RepositorySnapshot).where(RepositorySnapshot.shortlisted.is_(True))
    )
    assert snapshot is not None
    assert snapshot.metrics["star_growth"]["created_last_4w"] == 87
    assert "vs_upstream" not in snapshot.metrics["star_growth"]
    stored = session.get(AnalysisRun, analysis.id)
    assert stored is not None
    assert stored.status != "failed"
