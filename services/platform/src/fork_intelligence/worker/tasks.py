from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import dramatiq
from sqlalchemy import select

from fork_intelligence.config import get_settings
from fork_intelligence.db import get_session_factory
from fork_intelligence.models import AnalysisRun, JobRecord
from fork_intelligence.services.pipeline import AnalysisPipeline
from fork_intelligence.worker.broker import broker as broker


@dramatiq.actor(max_retries=3, min_backoff=5000, max_backoff=120_000, time_limit=3_000_000)
def analyze_repository(analysis_id: str, job_id: str) -> None:
    identifier = uuid.UUID(analysis_id)
    job_identifier = uuid.UUID(job_id)
    with get_session_factory()() as session:
        session.execute(
            select(AnalysisRun.id).where(AnalysisRun.id == identifier).with_for_update()
        ).scalar_one()
        job = session.execute(
            select(JobRecord).where(JobRecord.id == job_identifier).with_for_update()
        ).scalar_one()
        now = datetime.now(UTC)
        active = session.scalar(
            select(JobRecord.id).where(
                JobRecord.analysis_id == identifier,
                JobRecord.id != job_identifier,
                JobRecord.status == "running",
                JobRecord.lease_expires_at > now,
            )
        )
        if job.status == "completed" or active is not None:
            return
        if job.status == "running" and job.lease_expires_at and job.lease_expires_at > now:
            return
        job.status = "running"
        job.attempts += 1
        job.lease_expires_at = now + timedelta(seconds=get_settings().max_analysis_seconds + 60)
        session.commit()
        try:
            AnalysisPipeline(session).run(identifier)
            session.refresh(job)
            analysis_status = session.scalar(
                select(AnalysisRun.status).where(AnalysisRun.id == identifier)
            )
            job.status = "waiting_for_quota" if analysis_status == "partial" else "completed"
            job.lease_expires_at = None
            session.commit()
        except BaseException as exc:
            session.rollback()
            failed_job = session.get(JobRecord, job.id)
            if failed_job is not None:
                failed_job.status = "failed"
                failed_job.lease_expires_at = None
                failed_job.last_error = {
                    "type": type(exc).__name__,
                    "message": "Worker task failed",
                }
                session.commit()
            raise


def dispatch_analysis(analysis_id: uuid.UUID, job_id: uuid.UUID) -> str:
    message = analyze_repository.send(str(analysis_id), str(job_id))
    return message.message_id
