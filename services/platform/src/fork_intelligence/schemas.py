from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AnalysisMode = Literal["explore", "successor", "innovation", "compare"]
AnalysisStatus = Literal[
    "queued", "running", "partial", "completed", "failed", "cancelled", "cancelling"
]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class ProblemDetails(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class AnalysisConfiguration(BaseModel):
    max_forks: int | None = Field(default=None, ge=1, le=5000)
    max_shortlist: int | None = Field(default=None, ge=1, le=25)
    analysis_depth: Literal["metadata", "structural", "deep"] = "structural"


class AnalysisCreate(BaseModel):
    repository: str = Field(min_length=3, max_length=300)
    mode: AnalysisMode = "explore"
    configuration: AnalysisConfiguration = Field(default_factory=AnalysisConfiguration)


class AnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requested_identifier: str
    requested_repository_id: uuid.UUID | None
    root_repository_id: uuid.UUID | None
    network_id: uuid.UUID | None
    mode: str
    status: str
    stage: str
    progress: float
    configuration: dict[str, Any]
    sampling: dict[str, Any]
    quota_snapshot: dict[str, Any]
    warnings: list[dict[str, Any]]
    error: dict[str, Any] | None
    analysis_version: str
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    github_id: int
    owner: str
    name: str
    html_url: str
    default_branch: str
    is_fork: bool
    archived: bool
    disabled: bool
    metadata: dict[str, Any]
    depth: str
    shortlisted: bool
    metrics: dict[str, Any]
    provenance: dict[str, Any]
    classification: dict[str, Any] | None = None
    scores: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class PaginatedForks(BaseModel):
    items: list[RepositoryRead]
    limit: int
    total: int
    next_cursor: str | None


class OverviewRead(BaseModel):
    analysis: AnalysisRead
    counts: dict[str, int]
    rankings: dict[str, list[dict[str, Any]]]
    data_coverage: dict[str, Any]


class ComparisonCreate(BaseModel):
    repository_ids: list[uuid.UUID] = Field(min_length=3, max_length=3)

    @field_validator("repository_ids")
    @classmethod
    def unique_repositories(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("repository_ids must be unique")
        return value


class ComparisonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_id: uuid.UUID
    repository_ids: list[str]
    status: str
    result: dict[str, Any]
    evidence_ids: list[str]
    version: str
    created_at: datetime
    updated_at: datetime


class ClusterRead(BaseModel):
    id: uuid.UUID
    label: str
    summary: str
    member_repository_ids: list[uuid.UUID]
    representative_evidence_ids: list[str]
    algorithm: str
    labeling_method: str
    confidence: float


class ClusterCollection(BaseModel):
    items: list[ClusterRead]
    method: str
    analysis_version: str


class EvolutionRead(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    sampling: dict[str, Any]
    provenance: dict[str, Any]


class HealthRead(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, str] = Field(default_factory=dict)
