from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fork_intelligence.models import AnalysisRun, ProgressEvent


def emit_event(
    session: Session,
    analysis: AnalysisRun,
    event_type: str,
    *,
    stage: str | None = None,
    progress: float | None = None,
    payload: dict[str, Any] | None = None,
) -> ProgressEvent:
    session.execute(
        select(AnalysisRun.id).where(AnalysisRun.id == analysis.id).with_for_update()
    ).scalar_one()
    sequence = session.scalar(
        select(func.coalesce(func.max(ProgressEvent.sequence), 0)).where(
            ProgressEvent.analysis_id == analysis.id
        )
    )
    event = ProgressEvent(
        analysis_id=analysis.id,
        sequence=int(sequence or 0) + 1,
        event_type=event_type,
        stage=stage or analysis.stage,
        progress=analysis.progress if progress is None else progress,
        payload=payload or {},
    )
    session.add(event)
    return event


def require_analysis(session: Session, analysis_id: uuid.UUID) -> AnalysisRun:
    analysis = session.get(AnalysisRun, analysis_id)
    if analysis is None:
        from fork_intelligence.errors import PlatformError

        raise PlatformError("analysis_not_found", "Analysis does not exist", status_code=404)
    return analysis
