from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from fork_intelligence.db import Base

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")

CREDENTIAL_MODES = ("authenticated", "anonymous")
BRANCH_DECISIONS = ("selected", "excluded", "unevaluated")


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RepositoryNetwork(TimestampMixin, Base):
    __tablename__ = "repository_networks"

    id: Mapped[uuid.UUID] = uuid_pk()
    root_repository_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "repositories.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_repository_networks_root_repository_id",
        ),
        nullable=True,
    )
    github_network_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Repository(TimestampMixin, Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("owner", "name", name="uq_repository_owner_name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    network_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repository_networks.id", ondelete="SET NULL"), index=True
    )
    parent_repository_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="SET NULL")
    )
    source_repository_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="SET NULL")
    )
    owner: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    html_url: Mapped[str] = mapped_column(String(512), nullable=False)
    clone_url: Mapped[str] = mapped_column(String(512), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    is_fork: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)


class AnalysisRun(TimestampMixin, Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "credential_mode in ('authenticated', 'anonymous')",
            name="ck_analysis_run_credential_mode",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    requested_identifier: Mapped[str] = mapped_column(String(201), nullable=False)
    requested_repository_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="SET NULL")
    )
    root_repository_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="SET NULL")
    )
    network_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repository_networks.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(40), nullable=False, default="explore")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(40), nullable=False, default="validation")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    sampling: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    quota_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    credential_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="authenticated"
    )
    credential_mode_transitions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_VALUE, default=list, nullable=False
    )
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE, default=list, nullable=False)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON_VALUE)
    analysis_version: Mapped[str] = mapped_column(String(40), default="2026.07.1", nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RepositorySnapshot(TimestampMixin, Base):
    __tablename__ = "repository_snapshots"
    __table_args__ = (
        UniqueConstraint("analysis_id", "repository_id", name="uq_snapshot_analysis_repository"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    depth: Mapped[str] = mapped_column(String(24), default="metadata", nullable=False)
    shortlisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint(
            "analysis_id",
            "repository_id",
            "planner_version",
            "name",
            name="uq_branch_analysis_repo_planner_name",
        ),
        UniqueConstraint(
            "analysis_id",
            "repository_id",
            "planner_version",
            "priority",
            name="uq_branch_analysis_repo_planner_priority",
        ),
        CheckConstraint(
            "decision in ('selected', 'excluded', 'unevaluated')",
            name="ck_branch_decision",
        ),
        CheckConstraint(
            "decision = 'unevaluated' or selection_reason is not null",
            name="ck_branch_selection_reason_required",
        ),
        CheckConstraint(
            "decision = 'unevaluated' or (head_sha is not null and retrieval_time is not null)",
            name="ck_branch_observed_fields_required",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    head_sha: Mapped[str | None] = mapped_column(String(64))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="unevaluated")
    selection_reason: Mapped[str | None] = mapped_column(String(255))
    retrieval_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planner_version: Mapped[str] = mapped_column(String(40), nullable=False)


class EvidenceItem(TimestampMixin, Base):
    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    file_path: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)


class Classification(TimestampMixin, Base):
    __tablename__ = "classifications"
    __table_args__ = (
        UniqueConstraint(
            "analysis_id", "repository_id", "version", name="uq_classification_version"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE")
    )
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list, nullable=False)
    missing_inputs: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list, nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)


class ScoreSnapshot(TimestampMixin, Base):
    __tablename__ = "score_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "analysis_id", "repository_id", "dimension", "version", name="uq_score_version"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    raw_inputs: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    available_inputs: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list, nullable=False)
    missing_inputs: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list, nullable=False)
    depth: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)


class RepositoryComparison(TimestampMixin, Base):
    __tablename__ = "repository_comparisons"

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    repository_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="complete", nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list, nullable=False)
    version: Mapped[str] = mapped_column(String(40), default="2026.07.1", nullable=False)


class DevelopmentCluster(TimestampMixin, Base):
    __tablename__ = "development_clusters"

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    feature_vector: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    representative_evidence_ids: Mapped[list[str]] = mapped_column(
        JSON_VALUE, default=list, nullable=False
    )
    algorithm: Mapped[str] = mapped_column(String(80), nullable=False)
    labeling_method: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class ClusterMember(Base):
    __tablename__ = "cluster_members"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("development_clusters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    similarity: Mapped[float] = mapped_column(Float, nullable=False)


class ProgressEvent(Base):
    __tablename__ = "progress_events"
    __table_args__ = (
        UniqueConstraint("analysis_id", "sequence", name="uq_event_analysis_sequence"),
        Index("ix_progress_events_analysis_sequence", "analysis_id", "sequence"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    progress: Mapped[float] = mapped_column(Float, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StageCheckpoint(TimestampMixin, Base):
    __tablename__ = "stage_checkpoints"
    __table_args__ = (
        UniqueConstraint("analysis_id", "stage", name="uq_checkpoint_analysis_stage"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "analysis_runs.id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    cursor: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON_VALUE)


class JobRecord(TimestampMixin, Base):
    __tablename__ = "job_records"

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    broker_message_id: Mapped[str | None] = mapped_column(String(128))
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[dict[str, Any] | None] = mapped_column(JSON_VALUE)


class ExportArtifact(TimestampMixin, Base):
    __tablename__ = "export_artifacts"
    __table_args__ = (
        UniqueConstraint("analysis_id", "format", "version", name="uq_export_analysis_format"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_location: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
