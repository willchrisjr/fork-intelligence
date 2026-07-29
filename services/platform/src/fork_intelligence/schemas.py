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


CredentialMode = Literal["authenticated", "anonymous"]
BranchDecision = Literal["selected", "excluded", "unevaluated"]

#: The only provider-quota keys allowed across the API boundary. Anything else
#: on a stored snapshot is dropped rather than forwarded.
QUOTA_SNAPSHOT_FIELDS = (
    "limit",
    "remaining",
    "reset",
    "resource",
    "credential_mode",
    "node_count",
)


class ProviderQuotaRead(BaseModel):
    """Sanitized provider capacity. Only these fields ever cross the boundary."""

    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None
    resource: str | None = None
    credential_mode: str | None = None
    node_count: int | None = None


class CredentialModeTransitionRead(BaseModel):
    """One recorded change of effective credential mode."""

    from_mode: str
    to_mode: str
    reason: str
    coverage_limitation: str | None = None
    occurred_at: str | None = None


class ProviderAccessRead(BaseModel):
    """How provider access affected an analysis (AC-RA-AGA-001.2, 002.3, 003.1-.3).

    Carries the effective mode and capacity only; the operator credential itself
    has no representation here and none of these fields is derived from it.
    """

    credential_mode: str
    quota: ProviderQuotaRead
    transitions: list[CredentialModeTransitionRead] = Field(default_factory=list)
    coverage_limitations: list[str] = Field(default_factory=list)
    #: Set when access ran out entirely, naming the resumable condition
    #: (AC-RA-AGA-002.4). Absent on a healthy run.
    access_condition: dict[str, Any] | None = None


class BranchPlanCounts(BaseModel):
    """Branch coverage counts (AC-RA-RBP-004.1/.2).

    ``excluded_by_cap`` and ``unevaluated`` are kept apart on purpose: the first
    is a sampling choice, the second is missing data.
    """

    considered: int = 0
    selected: int = 0
    excluded_by_cap: int = 0
    unevaluated: int = 0
    structurally_analyzed: int = 0


class BranchPlanEntryRead(BaseModel):
    """One versioned branch-candidate decision."""

    model_config = ConfigDict(from_attributes=True)

    repository_id: uuid.UUID
    repository_full_name: str | None = None
    branch_name: str
    head_sha: str | None = None
    is_default: bool
    #: Ordering within the repository's plan. For a cap exclusion this is the
    #: candidate's position relative to the selected branches (AC-RA-RBP-002.2).
    priority: int
    decision: BranchDecision
    #: For an unevaluated candidate this names the missing input or failure
    #: rather than a definitive exclusion reason (AC-RA-RBP-002.3).
    selection_reason: str | None = None
    retrieval_time: datetime | None = None
    planner_version: str


class BranchPlanRead(BaseModel):
    """Analysis-level branch-plan disclosure (AC-RA-RBP-002.4).

    Deliberately carries counts, caps, version, and a bounded reason summary
    rather than every entry: an analysis spans many repositories, and the
    per-candidate list belongs on the fork detail where it stays bounded.
    """

    planner_version: str | None = None
    effective_cap: int | None = None
    counts: BranchPlanCounts = Field(default_factory=BranchPlanCounts)
    #: Selection reason -> number of candidates, so reasons are disclosed at
    #: analysis level without embedding an unbounded entry list.
    selection_reasons: dict[str, int] = Field(default_factory=dict)
    #: True when no branch beyond the default was structurally analyzed
    #: (AC-RA-RBP-004.3).
    structural_coverage_default_only: bool | None = None


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
    #: Provider-access and branch-plan projections. Optional so existing
    #: clients keep working against the previous shape.
    access: ProviderAccessRead | None = None
    branch_plan: BranchPlanRead | None = None

    @field_validator("quota_snapshot")
    @classmethod
    def sanitize_quota_snapshot(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Reduce the stored quota to known fields before it leaves the process.

        This field is a raw passthrough of whatever the worker persisted. The
        provider writers already sanitize, so this is the boundary backstop that
        keeps AC-RA-AGA-001.3 true even if some future writer puts credential
        material on the snapshot. Legitimate values are unaffected.
        """
        if not isinstance(value, dict):
            return {}
        return {key: value[key] for key in QUOTA_SNAPSHOT_FIELDS if key in value}


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
    #: Every considered candidate for this repository, bounded by the planner's
    #: own candidate cap (AC-RA-RBP-002.1).
    branch_plan: list[BranchPlanEntryRead] = Field(default_factory=list)


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
