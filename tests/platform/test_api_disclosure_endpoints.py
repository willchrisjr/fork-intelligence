from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from fork_intelligence.api.deps import get_db_session
from fork_intelligence.api.main import app
from fork_intelligence.db import Base
from fork_intelligence.models import (
    AnalysisRun,
    Branch,
    Repository,
    RepositoryNetwork,
    RepositorySnapshot,
)

TOKEN = "ghp-operator-secret"  # noqa: S105 - inert fixture value.


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    # TestClient serves requests on a different thread, so the in-memory
    # database must be a single shared connection rather than one per thread.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> dict[str, uuid.UUID]:
    """An analysis that fell back to anonymous with a planned, capped fork."""
    with session_factory() as session:
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

        analysis = AnalysisRun(
            requested_identifier="root/project",
            idempotency_key=f"idem-{uuid.uuid4()}",
            network_id=network.id,
            root_repository_id=root.id,
            status="completed",
            credential_mode="anonymous",
            quota_snapshot={"limit": 60, "remaining": 3, "resource": "core"},
            credential_mode_transitions=[
                {
                    "from_mode": "authenticated",
                    "to_mode": "anonymous",
                    "reason": "operator_credential_quota_exhausted",
                    "coverage_limitation": "Anonymous access lowers the rate limit.",
                    "occurred_at": "2026-07-22T00:00:00+00:00",
                }
            ],
            sampling={
                "branch_cap": 2,
                "branch_planner_version": "2026.07.2",
                "branches_structurally_analyzed": 2,
                "structural_coverage_default_only": False,
            },
        )
        session.add(analysis)
        session.flush()

        session.add_all(
            [
                RepositorySnapshot(
                    analysis_id=analysis.id, repository_id=fork.id, shortlisted=True
                ),
                Branch(
                    analysis_id=analysis.id,
                    repository_id=fork.id,
                    name="main",
                    head_sha="a" * 40,
                    is_default=True,
                    priority=0,
                    decision="selected",
                    selection_reason="default_branch",
                    retrieval_time=datetime.now(UTC),
                    planner_version="2026.07.2",
                ),
                Branch(
                    analysis_id=analysis.id,
                    repository_id=fork.id,
                    name="dropped",
                    head_sha="b" * 40,
                    is_default=False,
                    priority=1,
                    decision="excluded",
                    selection_reason="branch_cap_exceeded",
                    retrieval_time=datetime.now(UTC),
                    planner_version="2026.07.2",
                ),
            ]
        )
        session.commit()
        return {"analysis": analysis.id, "fork": fork.id}


def test_analysis_endpoint_discloses_access_and_branch_plan(
    client: TestClient, seeded: dict[str, uuid.UUID]
) -> None:
    response = client.get(f"/api/v1/analyses/{seeded['analysis']}")

    assert response.status_code == 200
    body = response.json()

    access = body["access"]
    assert access["credential_mode"] == "anonymous"
    assert access["quota"]["remaining"] == 3
    assert access["transitions"][0]["reason"] == "operator_credential_quota_exhausted"
    assert access["coverage_limitations"] == ["Anonymous access lowers the rate limit."]

    plan = body["branch_plan"]
    assert plan["planner_version"] == "2026.07.2"
    assert plan["effective_cap"] == 2
    assert plan["counts"]["selected"] == 1
    assert plan["counts"]["excluded_by_cap"] == 1
    assert plan["counts"]["considered"] == 2
    assert plan["selection_reasons"] == {"branch_cap_exceeded": 1, "default_branch": 1}
    assert plan["structural_coverage_default_only"] is False


def test_fork_detail_lists_every_considered_candidate(
    client: TestClient, seeded: dict[str, uuid.UUID]
) -> None:
    response = client.get(
        f"/api/v1/analyses/{seeded['analysis']}/forks/{seeded['fork']}"
    )

    assert response.status_code == 200
    entries = response.json()["branch_plan"]

    assert [entry["branch_name"] for entry in entries] == ["main", "dropped"]
    assert entries[0]["decision"] == "selected"
    assert entries[0]["is_default"] is True
    assert entries[1]["decision"] == "excluded"
    assert entries[1]["selection_reason"] == "branch_cap_exceeded"
    assert entries[1]["priority"] == 1
    assert entries[1]["head_sha"] == "b" * 40


def test_overview_carries_the_same_disclosure(
    client: TestClient, seeded: dict[str, uuid.UUID]
) -> None:
    response = client.get(f"/api/v1/analyses/{seeded['analysis']}/overview")

    assert response.status_code == 200
    analysis = response.json()["analysis"]
    assert analysis["access"]["credential_mode"] == "anonymous"
    assert analysis["branch_plan"]["counts"]["considered"] == 2


def test_no_endpoint_leaks_credential_material(
    client: TestClient, seeded: dict[str, uuid.UUID], session_factory: sessionmaker[Session]
) -> None:
    """AC-RA-AGA-001.3 asserted against real responses, not just the schema."""
    with session_factory() as session:
        analysis = session.get(AnalysisRun, seeded["analysis"])
        assert analysis is not None
        # Simulate a writer having stored something credential-shaped upstream.
        analysis.quota_snapshot = {**analysis.quota_snapshot, "authorization": f"Bearer {TOKEN}"}
        session.commit()

    bodies = [
        client.get(f"/api/v1/analyses/{seeded['analysis']}").text,
        client.get(f"/api/v1/analyses/{seeded['analysis']}/overview").text,
        client.get(f"/api/v1/analyses/{seeded['analysis']}/forks/{seeded['fork']}").text,
    ]

    for body in bodies:
        assert TOKEN not in body


def test_export_payload_shape_is_unchanged(
    client: TestClient, seeded: dict[str, uuid.UUID]
) -> None:
    """Export format is a separate work order; this one must not alter it."""
    response = client.get(f"/api/v1/analyses/{seeded['analysis']}/exports/json")

    assert response.status_code == 200
    analysis = response.json()["analysis"]
    assert "access" not in analysis
    assert "branch_plan" not in analysis
