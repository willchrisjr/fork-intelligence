from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import shutil
import uuid
from collections import Counter
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fork_intelligence.api.deps import get_db_session
from fork_intelligence.config import get_settings
from fork_intelligence.db import get_session_factory
from fork_intelligence.domain.comparisons import (
    ComparisonRepository,
    build_comparison_result,
)
from fork_intelligence.domain.exports import ExportFormat, render_export
from fork_intelligence.domain.repository_input import parse_repository_identifier
from fork_intelligence.errors import PlatformError
from fork_intelligence.models import (
    AnalysisRun,
    Branch,
    Classification,
    ClusterMember,
    DevelopmentCluster,
    EvidenceItem,
    ExportArtifact,
    JobRecord,
    ProgressEvent,
    Repository,
    RepositoryComparison,
    RepositoryNetwork,
    RepositorySnapshot,
    ScoreSnapshot,
)
from fork_intelligence.schemas import (
    AnalysisCreate,
    AnalysisRead,
    ClusterCollection,
    ClusterRead,
    ComparisonCreate,
    ComparisonRead,
    EvolutionRead,
    HealthRead,
    OverviewRead,
    PaginatedForks,
    RepositoryRead,
)
from fork_intelligence.services.events import emit_event, require_analysis
from fork_intelligence.worker.tasks import dispatch_analysis

router = APIRouter(prefix="/api/v1")
_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@router.get("/health/live", response_model=HealthRead, tags=["health"])
def live() -> HealthRead:
    return HealthRead(status="ok", checks={"process": "ok"})


@router.get("/health/ready", response_model=HealthRead, tags=["health"])
def ready(session: Annotated[Session, Depends(get_db_session)]) -> HealthRead:
    checks: dict[str, str] = {}
    try:
        session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
    try:
        redis = Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1)
        checks["redis"] = "ok" if redis.ping() else "unavailable"
        redis.close()
    except Exception:
        checks["redis"] = "unavailable"
    if any(value != "ok" for value in checks.values()):
        raise PlatformError(
            "service_not_ready",
            "A required dependency is unavailable",
            status_code=503,
            details=checks,
        )
    return HealthRead(status="ok", checks=checks)


@router.post(
    "/analyses",
    response_model=AnalysisRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["analyses"],
)
def create_analysis(
    body: AnalysisCreate,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AnalysisRun:
    identifier = parse_repository_identifier(body.repository)
    configuration = body.configuration.model_dump(exclude_none=True)
    settings = get_settings()
    configuration.setdefault("max_forks", settings.max_forks)
    configuration.setdefault("max_shortlist", settings.max_shortlist)
    configuration["max_forks"] = min(configuration["max_forks"], settings.max_forks)
    configuration["max_shortlist"] = min(configuration["max_shortlist"], settings.max_shortlist)
    canonical = json.dumps(
        {
            "repository": identifier.full_name.lower(),
            "mode": body.mode,
            "configuration": configuration,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    if idempotency_key is not None and not _IDEMPOTENCY.fullmatch(idempotency_key):
        raise PlatformError(
            "invalid_idempotency_key", "Idempotency-Key has invalid characters", status_code=422
        )
    key = idempotency_key or f"auto:{uuid.uuid4()}"
    existing = session.scalar(select(AnalysisRun).where(AnalysisRun.idempotency_key == key))
    if existing is not None:
        existing_canonical = json.dumps(
            {
                "repository": existing.requested_identifier.lower(),
                "mode": existing.mode,
                "configuration": existing.configuration,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        if existing_canonical != canonical:
            raise PlatformError(
                "idempotency_conflict",
                "Idempotency-Key was already used with a different request",
                status_code=409,
            )
        response.status_code = status.HTTP_200_OK
        return existing
    active_for_repository = session.scalar(
        select(AnalysisRun).where(
            func.lower(AnalysisRun.requested_identifier) == identifier.full_name.lower(),
            AnalysisRun.status.in_({"queued", "running", "cancelling"}),
        )
    )
    if active_for_repository is not None:
        raise PlatformError(
            "analysis_already_active",
            "An analysis for this repository is already queued or running",
            status_code=409,
            details={"analysis_id": str(active_for_repository.id)},
        )
    active_count = (
        session.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .where(AnalysisRun.status.in_({"queued", "running", "cancelling"}))
        )
        or 0
    )
    if active_count >= settings.max_active_analyses:
        raise PlatformError(
            "analysis_queue_full",
            "The analysis queue has reached its configured admission cap",
            status_code=503,
            details={"active": active_count, "limit": settings.max_active_analyses},
        )
    store_parent = settings.git_store_root.resolve().parent
    store_parent.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(store_parent).free
    if free_bytes < settings.min_git_free_bytes:
        raise PlatformError(
            "git_storage_low",
            "Analysis admission paused because Git storage is below its free-space watermark",
            status_code=503,
            details={"free_bytes": free_bytes, "minimum_free_bytes": settings.min_git_free_bytes},
        )
    analysis = AnalysisRun(
        requested_identifier=identifier.full_name,
        idempotency_key=key,
        mode=body.mode,
        configuration=configuration,
    )
    session.add(analysis)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        winner = session.scalar(select(AnalysisRun).where(AnalysisRun.idempotency_key == key))
        if winner is None:
            raise
        winner_canonical = json.dumps(
            {
                "repository": winner.requested_identifier.lower(),
                "mode": winner.mode,
                "configuration": winner.configuration,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        if winner_canonical != canonical:
            raise PlatformError(
                "idempotency_conflict",
                "Idempotency-Key was concurrently used with a different request",
                status_code=409,
            ) from exc
        response.status_code = status.HTTP_200_OK
        return winner
    emit_event(
        session,
        analysis,
        "analysis.queued",
        payload={"repository": identifier.full_name, "configuration": configuration},
    )
    job = JobRecord(analysis_id=analysis.id, job_type="analysis", status="queued")
    session.add(job)
    session.commit()
    try:
        job.broker_message_id = dispatch_analysis(analysis.id, job.id)
    except Exception:
        analysis.warnings = [
            *analysis.warnings,
            {
                "code": "broker_unavailable",
                "message": "Analysis is durable but dispatch is delayed; use resume to retry",
            },
        ]
        job.status = "dispatch_pending"
    session.commit()
    return analysis


@router.get("/analyses/{analysis_id}", response_model=AnalysisRead, tags=["analyses"])
def get_analysis(
    analysis_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]
) -> AnalysisRun:
    return require_analysis(session, analysis_id)


@router.get("/analyses/{analysis_id}/events", tags=["analyses"])
async def analysis_events(
    analysis_id: uuid.UUID,
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    require_analysis(session, analysis_id)
    try:
        after = max(0, int(last_event_id or 0))
    except ValueError as exc:
        raise PlatformError(
            "invalid_event_cursor", "Last-Event-ID must be an integer", status_code=422
        ) from exc
    return StreamingResponse(
        _event_stream(analysis_id, after, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/analyses/{analysis_id}/progress", include_in_schema=False)
async def progress_alias(
    analysis_id: uuid.UUID,
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    return await analysis_events(analysis_id, request, session, last_event_id)


async def _event_stream(analysis_id: uuid.UUID, after: int, request: Request) -> Any:
    settings = get_settings()
    sequence = after
    last_write = asyncio.get_running_loop().time()
    while not await request.is_disconnected():
        with get_session_factory()() as event_session:
            # Read terminal state first. Under READ COMMITTED, observing a terminal
            # state guarantees the subsequently queried terminal event is visible.
            terminal = event_session.scalar(
                select(AnalysisRun.status).where(AnalysisRun.id == analysis_id)
            ) in {"completed", "failed", "cancelled"}
            events = event_session.scalars(
                select(ProgressEvent)
                .where(
                    ProgressEvent.analysis_id == analysis_id,
                    ProgressEvent.sequence > sequence,
                )
                .order_by(ProgressEvent.sequence)
                .limit(100)
            ).all()
        for event in events:
            sequence = event.sequence
            data = {
                "type": event.event_type,
                "stage": event.stage,
                "progress": event.progress,
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
            }
            yield (f"id: {event.sequence}\ndata: {json.dumps(data, default=str)}\n\n")
            last_write = asyncio.get_running_loop().time()
        if terminal and not events:
            return
        if asyncio.get_running_loop().time() - last_write >= settings.sse_heartbeat_seconds:
            yield ": heartbeat\n\n"
            last_write = asyncio.get_running_loop().time()
        await asyncio.sleep(settings.sse_poll_seconds)


@router.get("/analyses/{analysis_id}/overview", response_model=OverviewRead, tags=["analyses"])
def analysis_overview(
    analysis_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]
) -> OverviewRead:
    analysis = require_analysis(session, analysis_id)
    classifications = session.scalars(
        select(Classification)
        .join(Repository, Repository.id == Classification.repository_id)
        .where(
            Classification.analysis_id == analysis_id,
            Repository.is_fork.is_(True),
        )
    ).all()
    counts = Counter(item.label for item in classifications)
    total = (
        session.scalar(
            select(func.count())
            .select_from(RepositorySnapshot)
            .where(RepositorySnapshot.analysis_id == analysis_id)
        )
        or 0
    )
    shortlisted = (
        session.scalar(
            select(func.count())
            .select_from(RepositorySnapshot)
            .join(Repository, Repository.id == RepositorySnapshot.repository_id)
            .where(
                RepositorySnapshot.analysis_id == analysis_id,
                RepositorySnapshot.shortlisted.is_(True),
                Repository.is_fork.is_(True),
            )
        )
        or 0
    )
    rankings: dict[str, list[dict[str, Any]]] = {}
    dimensions = session.scalars(
        select(ScoreSnapshot.dimension).where(ScoreSnapshot.analysis_id == analysis_id).distinct()
    ).all()
    for dimension in dimensions:
        rows = session.execute(
            select(ScoreSnapshot, Repository)
            .join(Repository, Repository.id == ScoreSnapshot.repository_id)
            .where(
                ScoreSnapshot.analysis_id == analysis_id,
                ScoreSnapshot.dimension == dimension,
                Repository.is_fork.is_(True),
            )
            .order_by(ScoreSnapshot.value.desc())
            .limit(5)
        ).all()
        rankings[dimension] = [
            {
                "repository_id": str(repository.id),
                "full_name": f"{repository.owner}/{repository.name}",
                "value": score.value,
                "confidence": score.confidence,
            }
            for score, repository in rows
        ]
    return OverviewRead(
        analysis=AnalysisRead.model_validate(analysis),
        counts={
            "repositories": total,
            "forks": max(0, total - 1),
            "shortlisted": shortlisted,
            **counts,
        },
        rankings=rankings,
        data_coverage={
            "structural": session.scalar(
                select(func.count())
                .select_from(RepositorySnapshot)
                .where(
                    RepositorySnapshot.analysis_id == analysis_id,
                    RepositorySnapshot.depth == "structural",
                )
            )
            or 0,
            "sampling": analysis.sampling,
        },
    )


@router.get("/analyses/{analysis_id}/forks", response_model=PaginatedForks, tags=["forks"])
def list_forks(
    analysis_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db_session)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    sort: str = "maintained_successor",
    order: Literal["asc", "desc"] = "desc",
    classification: str | None = None,
    depth: Literal["metadata", "structural", "deep"] | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> PaginatedForks:
    analysis = require_analysis(session, analysis_id)
    signature = hashlib.sha256(
        json.dumps(
            {
                "sort": sort,
                "order": order,
                "classification": classification,
                "depth": depth,
                "search": search,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    offset = _decode_cursor(cursor, signature)
    rows = [
        row for row in _fork_rows(session, analysis_id) if row[0].id != analysis.root_repository_id
    ]
    if classification:
        rows = [row for row in rows if row[2] is not None and row[2].label == classification]
    if depth:
        rows = [row for row in rows if row[1].depth == depth]
    if search:
        needle = search.casefold()
        rows = [row for row in rows if needle in f"{row[0].owner}/{row[0].name}".casefold()]
    reverse = order == "desc"
    rows.sort(key=lambda row: _sort_value(row, sort), reverse=reverse)
    total = len(rows)
    selected = rows[offset : offset + limit]
    next_offset = offset + len(selected)
    next_cursor = _encode_cursor(next_offset, signature) if next_offset < total else None
    return PaginatedForks(
        items=[_repository_read(*row) for row in selected],
        limit=limit,
        total=total,
        next_cursor=next_cursor,
    )


@router.get(
    "/analyses/{analysis_id}/forks/{repository_id}",
    response_model=RepositoryRead,
    tags=["forks"],
)
def fork_detail(
    analysis_id: uuid.UUID,
    repository_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db_session)],
) -> RepositoryRead:
    require_analysis(session, analysis_id)
    for row in _fork_rows(session, analysis_id, repository_id):
        result = _repository_read(*row)
        evidence = session.scalars(
            select(EvidenceItem)
            .where(
                EvidenceItem.analysis_id == analysis_id,
                EvidenceItem.repository_id == repository_id,
            )
            .order_by(EvidenceItem.created_at, EvidenceItem.id)
            .limit(500)
        ).all()
        return result.model_copy(
            update={
                "evidence": [
                    {
                        "id": str(item.id),
                        "type": item.evidence_type,
                        "source": item.source,
                        "source_url": item.source_url,
                        "commit_sha": item.commit_sha,
                        "file_path": item.file_path,
                        "payload": item.payload,
                        "provenance": item.provenance,
                    }
                    for item in evidence
                ]
            }
        )
    raise PlatformError(
        "fork_not_found", "Repository is not part of this analysis", status_code=404
    )


@router.get("/analyses/{analysis_id}/clusters", response_model=ClusterCollection, tags=["clusters"])
def list_clusters(
    analysis_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]
) -> ClusterCollection:
    analysis = require_analysis(session, analysis_id)
    clusters = session.scalars(
        select(DevelopmentCluster).where(DevelopmentCluster.analysis_id == analysis_id)
    ).all()
    items = [
        ClusterRead(
            id=cluster.id,
            label=cluster.label,
            summary=cluster.summary,
            member_repository_ids=list(
                session.scalars(
                    select(ClusterMember.repository_id).where(
                        ClusterMember.cluster_id == cluster.id
                    )
                ).all()
            ),
            representative_evidence_ids=cluster.representative_evidence_ids,
            algorithm=cluster.algorithm,
            labeling_method=cluster.labeling_method,
            confidence=cluster.confidence,
        )
        for cluster in clusters
    ]
    method = clusters[0].algorithm if clusters else "complete-link-agglomerative-2026.07.1"
    return ClusterCollection(
        items=items,
        method=method,
        analysis_version=analysis.analysis_version,
    )


@router.get("/analyses/{analysis_id}/evolution", response_model=EvolutionRead, tags=["analyses"])
def evolution(
    analysis_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]
) -> EvolutionRead:
    analysis = require_analysis(session, analysis_id)
    rows = _fork_rows(session, analysis_id)
    memberships = session.execute(
        select(ClusterMember.repository_id, ClusterMember.cluster_id)
        .join(DevelopmentCluster, DevelopmentCluster.id == ClusterMember.cluster_id)
        .where(DevelopmentCluster.analysis_id == analysis_id)
    ).all()
    cluster_by_repository = {repository_id: cluster_id for repository_id, cluster_id in memberships}
    nodes = [
        {
            "repository_id": str(repository.id),
            "full_name": f"{repository.owner}/{repository.name}",
            "is_root": repository.id == analysis.root_repository_id,
            "classification": classification.label if classification else "unknown",
            "cluster_id": (
                str(cluster_by_repository[repository.id])
                if repository.id in cluster_by_repository
                else None
            ),
            "depth": snapshot.depth,
            "metrics": snapshot.metrics,
        }
        for repository, snapshot, classification, _ in rows
    ]
    included = {repository.id for repository, _, _, _ in rows}
    edges = [
        {
            "source_repository_id": str(repository.parent_repository_id),
            "target_repository_id": str(repository.id),
            "relationship": "fork",
        }
        for repository, _, _, _ in rows
        if repository.parent_repository_id in included
    ]
    return EvolutionRead(
        nodes=nodes,
        edges=edges,
        sampling=analysis.sampling,
        provenance={
            "source": "github_rest_and_git",
            "github_api_version": get_settings().github_api_version,
            "analysis_version": analysis.analysis_version,
        },
    )


@router.post(
    "/analyses/{analysis_id}/comparisons",
    response_model=ComparisonRead,
    status_code=status.HTTP_201_CREATED,
    tags=["comparisons"],
)
def create_comparison(
    analysis_id: uuid.UUID,
    body: ComparisonCreate,
    session: Annotated[Session, Depends(get_db_session)],
) -> RepositoryComparison:
    analysis = require_analysis(session, analysis_id)
    snapshots = session.scalars(
        select(RepositorySnapshot).where(
            RepositorySnapshot.analysis_id == analysis_id,
            RepositorySnapshot.repository_id.in_(body.repository_ids),
        )
    ).all()
    if len(snapshots) != len(body.repository_ids):
        raise PlatformError(
            "invalid_comparison", "All repositories must belong to the analysis", status_code=422
        )
    root_id = session.scalar(
        select(RepositoryNetwork.root_repository_id).where(
            RepositoryNetwork.id == analysis.network_id
        )
    )
    if root_id not in body.repository_ids:
        raise PlatformError(
            "upstream_required",
            "Comparison must include the network root repository",
            status_code=422,
        )
    snapshots_by_id = {snapshot.repository_id: snapshot for snapshot in snapshots}
    repositories = session.scalars(
        select(Repository).where(Repository.id.in_(body.repository_ids))
    ).all()
    repositories_by_id = {repository.id: repository for repository in repositories}
    branches = session.scalars(
        select(Branch).where(
            Branch.analysis_id == analysis_id,
            Branch.repository_id.in_(body.repository_ids),
            Branch.is_default.is_(True),
        )
    ).all()
    heads_by_repository = {branch.repository_id: branch.head_sha for branch in branches}
    comparison_inputs = [
        ComparisonRepository(
            repository_id=str(repository_id),
            full_name=(
                f"{repositories_by_id[repository_id].owner}/"
                f"{repositories_by_id[repository_id].name}"
            ),
            role="upstream" if repository_id == root_id else "fork",
            default_branch=repositories_by_id[repository_id].default_branch,
            head_sha=heads_by_repository.get(repository_id),
            metrics=snapshots_by_id[repository_id].metrics,
        )
        for repository_id in body.repository_ids
    ]
    result = build_comparison_result(comparison_inputs)
    evidence_items = session.scalars(
        select(EvidenceItem)
        .where(
            EvidenceItem.analysis_id == analysis_id,
            EvidenceItem.repository_id.in_(body.repository_ids),
        )
        .order_by(EvidenceItem.created_at, EvidenceItem.id)
        .limit(250)
    ).all()
    evidence_ids = [str(item.id) for item in evidence_items]
    result["evidence"] = [
        {
            "id": str(item.id),
            "type": item.evidence_type,
            "title": item.payload.get("title") or item.evidence_type.replace("_", " ").title(),
            "summary": item.payload.get("summary")
            or (
                "Git evidence includes merge-base, ahead/behind, unique commit, patch, "
                "changed-file, and conflict-approximation details."
                if item.source == "git"
                else "Repository metadata used by the deterministic comparison."
            ),
            "repository_id": str(item.repository_id) if item.repository_id else None,
            "source_url": item.source_url,
            "reference": item.commit_sha or item.file_path,
            "confidence": item.provenance.get("confidence"),
            "provenance": item.provenance,
        }
        for item in evidence_items
    ]
    missing_blob_count = sum(
        int((snapshot.metrics.get("patch_coverage") or {}).get("missing_blobs") or 0)
        for snapshot in snapshots
    )
    result["missing_data"] = (
        [f"{missing_blob_count} commit patches were unavailable because blobs were not hydrated"]
        if missing_blob_count
        else []
    )
    comparison = RepositoryComparison(
        analysis_id=analysis_id,
        repository_ids=[str(identifier) for identifier in body.repository_ids],
        result=result,
        evidence_ids=evidence_ids,
    )
    session.add(comparison)
    session.commit()
    return comparison


@router.get("/comparisons/{comparison_id}", response_model=ComparisonRead, tags=["comparisons"])
def get_comparison(
    comparison_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]
) -> RepositoryComparison:
    comparison = session.get(RepositoryComparison, comparison_id)
    if comparison is None:
        raise PlatformError("comparison_not_found", "Comparison does not exist", status_code=404)
    return comparison


@router.get("/analyses/{analysis_id}/exports/{format_name}", tags=["exports"])
def export_analysis(
    analysis_id: uuid.UUID,
    format_name: ExportFormat,
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
) -> Response:
    analysis = require_analysis(session, analysis_id)
    if analysis.status not in {"completed", "failed", "cancelled", "partial"}:
        raise PlatformError(
            "analysis_not_sealed",
            "Exports are available only after analysis reaches a durable terminal checkpoint",
            status_code=409,
        )
    artifact = session.scalar(
        select(ExportArtifact).where(
            ExportArtifact.analysis_id == analysis_id,
            ExportArtifact.format == format_name,
            ExportArtifact.version == analysis.analysis_version,
        )
    )
    if artifact is None:
        rows = _fork_rows(session, analysis_id)
        upstream_rows = [row for row in rows if row[0].id == analysis.root_repository_id]
        fork_rows = [row for row in rows if row[0].id != analysis.root_repository_id]
        payload = {
            "analysis": AnalysisRead.model_validate(analysis).model_dump(mode="json"),
            "generated_at": (
                analysis.completed_at or analysis.updated_at or analysis.created_at
            ).isoformat(),
            "source_provenance": {
                "github_api_version": get_settings().github_api_version,
                "analysis_version": analysis.analysis_version,
            },
            "configuration": analysis.configuration,
            "upstream": _export_fork(*upstream_rows[0]) if upstream_rows else None,
            "forks": [_export_fork(*row) for row in fork_rows],
            "known_limitations": [
                warning.get("message", warning.get("code")) for warning in analysis.warnings
            ],
        }
        content, media_type = render_export(payload, format_name)
        digest = hashlib.sha256(content).hexdigest()
        artifact = ExportArtifact(
            analysis_id=analysis_id,
            format=format_name,
            content_hash=digest,
            storage_location=f"database:{digest}",
            size_bytes=len(content),
            content=content.decode(),
            version=analysis.analysis_version,
        )
        session.add(artifact)
        session.commit()
    else:
        content = artifact.content.encode()
        digest = artifact.content_hash
        media_type = {
            "json": "application/json",
            "csv": "text/csv; charset=utf-8",
            "markdown": "text/markdown; charset=utf-8",
        }[format_name]
    extension = "md" if format_name == "markdown" else format_name
    etag = f'"{digest}"'
    if request.headers.get("If-None-Match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="analysis-{analysis_id}.{extension}"',
            "ETag": etag,
        },
    )


@router.post("/analyses/{analysis_id}/cancel", response_model=AnalysisRead, tags=["analyses"])
def cancel_analysis(
    analysis_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]
) -> AnalysisRun:
    analysis = require_analysis(session, analysis_id)
    if analysis.status in {"completed", "failed", "cancelled", "cancelling"}:
        return analysis
    analysis.cancel_requested = True
    analysis.status = "cancelling"
    emit_event(session, analysis, "analysis.cancel_requested")
    session.commit()
    return analysis


@router.post("/analyses/{analysis_id}/resume", response_model=AnalysisRead, tags=["analyses"])
def resume_analysis(
    analysis_id: uuid.UUID, session: Annotated[Session, Depends(get_db_session)]
) -> AnalysisRun:
    analysis = require_analysis(session, analysis_id)
    if analysis.status == "queued":
        pending_job = session.scalar(
            select(JobRecord)
            .where(
                JobRecord.analysis_id == analysis.id,
                JobRecord.status.in_({"queued", "dispatch_pending"}),
            )
            .order_by(JobRecord.created_at.desc())
            .limit(1)
        )
        if pending_job is not None:
            try:
                # Safe redispatch is keyed by the durable job row. Duplicate broker
                # deliveries serialize on that row and exit when a live lease exists.
                pending_job.broker_message_id = dispatch_analysis(analysis.id, pending_job.id)
                pending_job.status = "queued"
            except Exception:
                pending_job.status = "dispatch_pending"
            session.commit()
        return analysis
    if analysis.status in {"completed", "running", "cancelling"}:
        return analysis
    if analysis.status not in {"failed", "cancelled", "partial"}:
        return analysis
    analysis.cancel_requested = False
    analysis.status = "queued"
    analysis.error = None
    emit_event(session, analysis, "analysis.resume_queued")
    job = JobRecord(analysis_id=analysis.id, job_type="analysis", status="queued")
    session.add(job)
    session.commit()
    try:
        job.broker_message_id = dispatch_analysis(analysis.id, job.id)
    except Exception:
        job.status = "dispatch_pending"
        analysis.warnings = [
            *analysis.warnings,
            {
                "code": "broker_unavailable",
                "message": "Resume is durable but dispatch is delayed",
            },
        ]
    session.commit()
    return analysis


def _fork_rows(
    session: Session, analysis_id: uuid.UUID, repository_id: uuid.UUID | None = None
) -> list[tuple[Repository, RepositorySnapshot, Classification | None, list[ScoreSnapshot]]]:
    statement = (
        select(Repository, RepositorySnapshot, Classification)
        .join(RepositorySnapshot, RepositorySnapshot.repository_id == Repository.id)
        .outerjoin(
            Classification,
            (Classification.repository_id == Repository.id)
            & (Classification.analysis_id == analysis_id),
        )
        .where(RepositorySnapshot.analysis_id == analysis_id)
    )
    if repository_id is not None:
        statement = statement.where(Repository.id == repository_id)
    rows = session.execute(statement).all()
    result = []
    for repository, snapshot, classification in rows:
        scores = list(
            session.scalars(
                select(ScoreSnapshot).where(
                    ScoreSnapshot.analysis_id == analysis_id,
                    ScoreSnapshot.repository_id == repository.id,
                )
            ).all()
        )
        result.append((repository, snapshot, classification, scores))
    return result


def _repository_read(
    repository: Repository,
    snapshot: RepositorySnapshot,
    classification: Classification | None,
    scores: list[ScoreSnapshot],
) -> RepositoryRead:
    return RepositoryRead(
        id=repository.id,
        github_id=repository.github_id,
        owner=repository.owner,
        name=repository.name,
        html_url=repository.html_url,
        default_branch=repository.default_branch,
        is_fork=repository.is_fork,
        archived=repository.archived,
        disabled=repository.disabled,
        metadata=repository.metadata_json,
        depth=snapshot.depth,
        shortlisted=snapshot.shortlisted,
        metrics=snapshot.metrics,
        provenance=snapshot.provenance,
        classification=(
            {
                "label": classification.label,
                "confidence": classification.confidence,
                "reasons": classification.reasons,
                "missing_inputs": classification.missing_inputs,
                "evidence_ids": classification.evidence_ids,
                "version": classification.version,
            }
            if classification
            else None
        ),
        scores=[
            {
                "dimension": score.dimension,
                "value": score.value,
                "confidence": score.confidence,
                "available_inputs": score.available_inputs,
                "missing_inputs": score.missing_inputs,
                "raw_inputs": score.raw_inputs,
                "version": score.version,
            }
            for score in scores
        ],
    )


def _sort_value(
    row: tuple[Repository, RepositorySnapshot, Classification | None, list[ScoreSnapshot]],
    sort: str,
) -> Any:
    repository, snapshot, _, scores = row
    score = next((item.value for item in scores if item.dimension == sort), None)
    if score is not None:
        return (score, repository.owner.casefold(), repository.name.casefold())
    if sort in {"stars", "days_since_push", "unique_patches", "ahead", "behind"}:
        return (
            snapshot.metrics.get(sort, snapshot.raw_metadata.get(sort, 0)) or 0,
            repository.owner.casefold(),
            repository.name.casefold(),
        )
    if sort == "name":
        return (repository.owner.casefold(), repository.name.casefold())
    raise PlatformError("invalid_sort", "Unsupported fork sort field", status_code=422)


def _encode_cursor(offset: int, signature: str) -> str:
    payload = json.dumps({"offset": offset, "signature": signature}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str | None, signature: str) -> int:
    if cursor is None:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode())
        if data["signature"] != signature or int(data["offset"]) < 0:
            raise ValueError
        return int(data["offset"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise PlatformError(
            "invalid_cursor", "Cursor does not match this query", status_code=422
        ) from exc


def _export_fork(
    repository: Repository,
    snapshot: RepositorySnapshot,
    classification: Classification | None,
    scores: list[ScoreSnapshot],
) -> dict[str, Any]:
    return {
        "repository_id": str(repository.id),
        "full_name": f"{repository.owner}/{repository.name}",
        "classification": classification.label if classification else "unknown",
        "confidence": classification.confidence if classification else 0,
        "depth": snapshot.depth,
        "stars": snapshot.metrics.get("stars", 0),
        "days_since_push": snapshot.metrics.get("days_since_push"),
        "unique_patches": snapshot.metrics.get("unique_patches"),
        "metrics": snapshot.metrics,
        "scores": {score.dimension: score.value for score in scores},
        "provenance": snapshot.provenance,
    }
