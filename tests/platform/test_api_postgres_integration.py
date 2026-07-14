from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fork_intelligence.api import routes
from fork_intelligence.api.main import app
from fork_intelligence.db import get_session_factory, reset_db_caches
from fork_intelligence.models import AnalysisRun, JobRecord
from fork_intelligence.services.events import emit_event

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def client() -> TestClient:
    if os.environ.get("FORK_INTELLIGENCE_RUN_POSTGRES_TESTS") != "1":
        pytest.skip("set FORK_INTELLIGENCE_RUN_POSTGRES_TESTS=1 for PostgreSQL integration tests")
    reset_db_caches()
    with TestClient(app) as test_client:
        yield test_client
    reset_db_caches()


def test_problem_details_and_health(client: TestClient) -> None:
    response = client.post("/api/v1/analyses", json={"repository": "https://example.com/x/y"})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "invalid_repository"

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"] == {"database": "ok", "redis": "ok"}


def test_durable_dispatch_resume_export_and_terminal_sse(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatches: list[str] = []

    def fake_dispatch(analysis_id: object, job_id: object) -> str:
        dispatches.append(f"{analysis_id}:{job_id}")
        return f"message-{len(dispatches)}"

    monkeypatch.setattr(routes, "dispatch_analysis", fake_dispatch)
    headers = {"Idempotency-Key": f"postgres-integration-{uuid.uuid4()}"}
    body = {"repository": "octocat/Hello-World", "mode": "explore"}
    created = client.post("/api/v1/analyses", json=body, headers=headers)
    assert created.status_code == 202
    analysis_id = created.json()["id"]
    analysis_uuid = uuid.UUID(analysis_id)

    replay = client.post("/api/v1/analyses", json=body, headers=headers)
    assert replay.status_code == 200
    assert replay.json()["id"] == analysis_id
    conflict = client.post(
        "/api/v1/analyses",
        json={"repository": "octocat/Spoon-Knife", "mode": "explore"},
        headers=headers,
    )
    assert conflict.status_code == 409

    session_factory = get_session_factory()
    with session_factory() as session:
        analysis = session.get(AnalysisRun, analysis_uuid)
        assert analysis is not None
        job = session.scalar(select(JobRecord).where(JobRecord.analysis_id == analysis.id))
        assert job is not None
        assert job.broker_message_id == "message-1"

    # A durable queued job can be safely redispatched even if Redis lost the
    # historical message while its database message ID remained populated.
    resumed = client.post(f"/api/v1/analyses/{analysis_id}/resume")
    assert resumed.status_code == 200
    assert len(dispatches) == 2
    with session_factory() as session:
        job = session.scalar(select(JobRecord).where(JobRecord.analysis_id == analysis_uuid))
        assert job is not None
        assert job.broker_message_id == "message-2"

    unsealed = client.get(f"/api/v1/analyses/{analysis_id}/exports/json")
    assert unsealed.status_code == 409
    assert unsealed.json()["code"] == "analysis_not_sealed"

    with session_factory() as session:
        analysis = session.get(AnalysisRun, analysis_uuid)
        assert analysis is not None
        analysis.status = "completed"
        analysis.stage = "complete"
        analysis.progress = 1.0
        analysis.completed_at = datetime.now(UTC)
        emit_event(session, analysis, "analysis.completed", progress=1.0)
        session.commit()

    first_export = client.get(f"/api/v1/analyses/{analysis_id}/exports/json")
    second_export = client.get(f"/api/v1/analyses/{analysis_id}/exports/json")
    assert first_export.status_code == second_export.status_code == 200
    assert first_export.content == second_export.content
    assert first_export.headers["etag"] == second_export.headers["etag"]
    unchanged = client.get(
        f"/api/v1/analyses/{analysis_id}/exports/json",
        headers={"If-None-Match": first_export.headers["etag"]},
    )
    assert unchanged.status_code == 304

    events = client.get(
        f"/api/v1/analyses/{analysis_id}/events",
        headers={"Last-Event-ID": "1"},
    )
    assert events.status_code == 200
    assert '"type": "analysis.completed"' in events.text
