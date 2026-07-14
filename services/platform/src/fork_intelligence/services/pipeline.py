from __future__ import annotations

import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from fork_intelligence.adapters.git import BareNetworkStore
from fork_intelligence.adapters.github import GitHubClient
from fork_intelligence.config import Settings, get_settings
from fork_intelligence.domain.classification import classify_repository
from fork_intelligence.domain.clustering import build_vector, cluster_vectors
from fork_intelligence.domain.repository_input import parse_repository_identifier
from fork_intelligence.domain.scoring import calculate_scores
from fork_intelligence.errors import GitHubError, PlatformError
from fork_intelligence.models import (
    AnalysisRun,
    Branch,
    Classification,
    ClusterMember,
    DevelopmentCluster,
    EvidenceItem,
    Repository,
    RepositoryNetwork,
    RepositorySnapshot,
    ScoreSnapshot,
    StageCheckpoint,
)
from fork_intelligence.services.events import emit_event, require_analysis


class AnalysisCancelled(Exception):
    pass


class AnalysisPipeline:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        github: GitHubClient | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.github = github or GitHubClient(self.settings)
        self._owns_github = github is None

    def run(self, analysis_id: uuid.UUID) -> None:
        analysis = require_analysis(self.session, analysis_id)
        if analysis.status == "completed":
            return
        analysis.status = "running"
        analysis.started_at = analysis.started_at or datetime.now(UTC)
        analysis.error = None
        emit_event(self.session, analysis, "analysis.started")
        self.session.commit()
        try:
            self._resolve(analysis)
            self._census(analysis)
            self._shortlist(analysis)
            if analysis.configuration.get("analysis_depth", "structural") != "metadata":
                self._structural(analysis)
            self._score_and_classify(analysis)
            self._cluster(analysis)
            self._stage(analysis, "exports", 0.95)
            self._finish_stage(analysis, "exports", {"generated_on_demand": True})
            analysis.status = "completed"
            analysis.stage = "complete"
            analysis.progress = 1.0
            analysis.completed_at = datetime.now(UTC)
            emit_event(self.session, analysis, "analysis.completed", progress=1.0)
            self.session.commit()
        except AnalysisCancelled:
            analysis.status = "cancelled"
            analysis.stage = "cancelled"
            analysis.completed_at = datetime.now(UTC)
            emit_event(self.session, analysis, "analysis.cancelled")
            self.session.commit()
        except GitHubError as exc:
            if exc.code != "github_rate_limited":
                self.session.rollback()
                analysis = require_analysis(self.session, analysis_id)
                analysis.status = "failed"
                analysis.error = {"code": exc.code, "message": exc.message}
                emit_event(self.session, analysis, "analysis.failed", payload=analysis.error)
                self.session.commit()
                raise
            self.session.rollback()
            analysis = require_analysis(self.session, analysis_id)
            analysis.status = "partial"
            analysis.stage = "waiting_for_quota"
            analysis.error = {
                "code": exc.code,
                "message": "GitHub quota was exhausted; resume after the documented reset",
                "details": exc.details,
            }
            warning = {
                "code": "github_rate_limited",
                "message": "Partial evidence is preserved; resume after GitHub quota resets",
                "quota": exc.details.get("quota", {}),
            }
            analysis.warnings = [*analysis.warnings, warning]
            emit_event(self.session, analysis, "analysis.waiting_for_quota", payload=warning)
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            analysis = require_analysis(self.session, analysis_id)
            analysis.status = "failed"
            analysis.error = {
                "code": exc.code if isinstance(exc, PlatformError) else "analysis_failed",
                "message": exc.message if isinstance(exc, PlatformError) else "Analysis failed",
            }
            emit_event(self.session, analysis, "analysis.failed", payload=analysis.error)
            self.session.commit()
            raise
        finally:
            if self._owns_github:
                self.github.close()

    def _resolve(self, analysis: AnalysisRun) -> None:
        if self._stage_complete(analysis, "resolution"):
            return
        self._stage(analysis, "resolution", 0.05)
        identifier = parse_repository_identifier(analysis.requested_identifier)
        requested_data = self.github.get_repository(identifier.owner, identifier.name)
        source = requested_data.get("source")
        root_data = requested_data
        if source and source["full_name"].lower() != requested_data["full_name"].lower():
            source_identifier = parse_repository_identifier(source["full_name"])
            root_data = self.github.get_repository(source_identifier.owner, source_identifier.name)

        network = self.session.scalar(
            select(RepositoryNetwork).where(
                RepositoryNetwork.github_network_id == f"github:{root_data['github_id']}"
            )
        )
        if network is None:
            network = RepositoryNetwork(github_network_id=f"github:{root_data['github_id']}")
            self.session.add(network)
            self.session.flush()
        root = self._upsert_repository(root_data, network.id)
        requested = self._upsert_repository(requested_data, network.id)
        network.root_repository_id = root.id
        network.last_refreshed_at = datetime.now(UTC)
        analysis.network_id = network.id
        analysis.requested_repository_id = requested.id
        analysis.root_repository_id = root.id
        self._upsert_snapshot(analysis.id, root, root_data)
        self._upsert_snapshot(analysis.id, requested, requested_data)
        self._finish_stage(
            analysis,
            "resolution",
            {"requested_repository_id": str(requested.id), "root_repository_id": str(root.id)},
        )

    def _census(self, analysis: AnalysisRun) -> None:
        if self._stage_complete(analysis, "census"):
            return
        self._stage(analysis, "census", 0.15)
        root = self._root_repository(analysis)
        discovered = list(
            self.session.scalars(
                select(Repository)
                .join(RepositorySnapshot, RepositorySnapshot.repository_id == Repository.id)
                .where(RepositorySnapshot.analysis_id == analysis.id)
            ).all()
        )
        seen = {repository.github_id for repository in discovered}
        traversed: set[int] = set()
        queue = deque(sorted(discovered, key=lambda repository: repository.github_id))
        max_forks = min(
            int(analysis.configuration.get("max_forks") or self.settings.max_forks),
            self.settings.max_forks,
        )
        request_budget = self.settings.max_github_requests
        if self.settings.github_token is None:
            request_budget = min(request_budget, 45)
        capped = False
        page_cap_reached = False
        requests_used = 0
        while queue and requests_used < request_budget and not capped:
            parent = queue.popleft()
            if parent.github_id in traversed:
                continue
            traversed.add(parent.github_id)
            remaining_requests = request_budget - requests_used
            page_cap = min(self.settings.max_github_pages, remaining_requests)
            for page in self.github.iter_forks(parent.owner, parent.name, max_pages=page_cap):
                requests_used += 1
                if page.has_next and page.page >= page_cap:
                    page_cap_reached = True
                for item in page.items:
                    if item["github_id"] in seen:
                        continue
                    if len(seen) - 1 >= max_forks:
                        capped = True
                        break
                    repository = self._upsert_repository(item, analysis.network_id)
                    repository.parent_repository_id = parent.id
                    repository.source_repository_id = root.id
                    self._upsert_snapshot(analysis.id, repository, item)
                    seen.add(repository.github_id)
                    queue.append(repository)
                analysis.quota_snapshot = page.quota
                checkpoint = self.session.scalar(
                    select(StageCheckpoint).where(
                        StageCheckpoint.analysis_id == analysis.id,
                        StageCheckpoint.stage == "census",
                    )
                )
                if checkpoint is not None:
                    checkpoint.cursor = {
                        "parent_github_id": parent.github_id,
                        "page": page.page,
                        "requests_used": requests_used,
                        "repositories_discovered": len(seen) - 1,
                    }
                emit_event(
                    self.session,
                    analysis,
                    "census.page_persisted",
                    payload={
                        "parent_repository_id": str(parent.id),
                        "page": page.page,
                        "repositories_discovered": len(seen) - 1,
                        "has_next": page.has_next,
                    },
                )
                self.session.commit()
                self._check_cancelled(analysis)
                if capped:
                    break
        traversal_incomplete = bool(queue) and requests_used >= request_budget
        analysis.sampling = {
            "expected_network_size": int(root.metadata_json.get("forks") or 0) + 1,
            "accessible_forks": len(seen) - 1,
            "fork_cap": max_forks,
            "forks_capped": capped,
            "github_page_cap": self.settings.max_github_pages,
            "github_request_cap": request_budget,
            "github_request_cap_authenticated": self.settings.github_token is not None,
            "nested_traversal_incomplete": traversal_incomplete,
            "github_page_cap_reached": page_cap_reached,
            "incomplete_reasons": [
                reason
                for condition, reason in (
                    (capped, "fork_cap_reached"),
                    (traversal_incomplete, "github_request_budget_reached"),
                    (page_cap_reached, "github_page_cap_reached"),
                )
                if condition
            ],
        }
        if capped:
            analysis.warnings = [
                *analysis.warnings,
                {"code": "fork_census_capped", "message": "Fork census reached its configured cap"},
            ]
        if traversal_incomplete:
            analysis.warnings = [
                *analysis.warnings,
                {
                    "code": "nested_traversal_incomplete",
                    "message": "Nested fork traversal reached its API request budget",
                },
            ]
        if page_cap_reached:
            analysis.warnings = [
                *analysis.warnings,
                {
                    "code": "github_page_cap_reached",
                    "message": "At least one fork page sequence exceeded its configured page cap",
                },
            ]
        self._finish_stage(
            analysis,
            "census",
            {"repositories_discovered": len(seen) - 1, "requests_used": requests_used},
        )

    def _shortlist(self, analysis: AnalysisRun) -> None:
        if self._stage_complete(analysis, "shortlist"):
            return
        self._stage(analysis, "shortlist", 0.35)
        root = self._root_repository(analysis)
        snapshots = self.session.scalars(
            select(RepositorySnapshot).where(
                RepositorySnapshot.analysis_id == analysis.id,
                RepositorySnapshot.repository_id != root.id,
            )
        ).all()
        shortlist_cap = min(
            int(analysis.configuration.get("max_shortlist") or self.settings.max_shortlist),
            self.settings.max_shortlist,
        )
        ranked = sorted(
            snapshots,
            key=lambda snapshot: (
                int(snapshot.raw_metadata.get("stars") or 0),
                str(snapshot.raw_metadata.get("pushed_at") or ""),
                int(snapshot.raw_metadata.get("forks") or 0),
            ),
            reverse=True,
        )
        selected = {snapshot.repository_id for snapshot in ranked[:shortlist_cap]}
        for snapshot in snapshots:
            snapshot.shortlisted = snapshot.repository_id in selected
        self._finish_stage(analysis, "shortlist", {"shortlisted": len(selected)})

    def _structural(self, analysis: AnalysisRun) -> None:
        if self._stage_complete(analysis, "structural"):
            return
        self._stage(analysis, "structural", 0.45)
        root = self._root_repository(analysis)
        store = BareNetworkStore(str(analysis.network_id), self.settings)
        root_branch = self.github.get_branch(root.owner, root.name, root.default_branch)
        root_ref = store.fetch_branch(
            str(analysis.id),
            root.github_id,
            root.owner,
            root.name,
            root.default_branch,
            root_branch["head_sha"],
        )
        self._upsert_branch(analysis.id, root, root_branch, True)
        snapshots = self.session.scalars(
            select(RepositorySnapshot)
            .where(
                RepositorySnapshot.analysis_id == analysis.id,
                RepositorySnapshot.shortlisted.is_(True),
                RepositorySnapshot.repository_id != root.id,
            )
            .limit(self.settings.max_deep_repositories)
        ).all()
        completed = 0
        for snapshot in snapshots:
            self._check_cancelled(analysis)
            repository = self.session.get(Repository, snapshot.repository_id)
            if repository is None or repository.disabled:
                continue
            try:
                branch = self.github.get_branch(
                    repository.owner, repository.name, repository.default_branch
                )
                fork_ref = store.fetch_branch(
                    str(analysis.id),
                    repository.github_id,
                    repository.owner,
                    repository.name,
                    repository.default_branch,
                    branch["head_sha"],
                )
                self._upsert_branch(analysis.id, repository, branch, True)
                comparison = store.compare(
                    root_ref,
                    fork_ref,
                    timeout=self._remaining_analysis_seconds(analysis),
                )
                changed_paths = [item["path"] for item in comparison.changed_files]
                snapshot.depth = "structural"
                snapshot.metrics = {
                    **snapshot.metrics,
                    "ahead": comparison.ahead,
                    "behind": comparison.behind,
                    "shared_commits": comparison.shared_commits,
                    "merge_base": comparison.merge_base,
                    "unique_commits": len(comparison.unique_commits),
                    "unique_patches": len(set(comparison.patch_ids.values())),
                    "patch_fingerprints": sorted(set(comparison.patch_ids.values())),
                    "aggregate_patch_id": comparison.patch_overlap.get("fork_aggregate_patch_id"),
                    "files_changed": len(comparison.changed_files),
                    "directories_changed": len(comparison.directory_summary),
                    "source_files_changed": comparison.file_composition["application_source"],
                    "test_files_changed": comparison.file_composition["tests"],
                    "file_composition": comparison.file_composition,
                    "directory_summary": comparison.directory_summary,
                    "changed_paths": changed_paths,
                    "conflict_estimate": comparison.conflict_estimate["value"],
                    "patch_coverage": {
                        "available": len(comparison.patch_ids),
                        "missing_blobs": len(comparison.missing_blob_commits),
                    },
                }
                evidence = EvidenceItem(
                    analysis_id=analysis.id,
                    repository_id=repository.id,
                    evidence_type="calculated_metric",
                    source="git",
                    source_url=f"{repository.html_url}/compare/{comparison.merge_base}...{branch['head_sha']}",
                    payload={
                        "merge_base": comparison.merge_base,
                        "ahead": comparison.ahead,
                        "behind": comparison.behind,
                        "unique_commits": comparison.unique_commits,
                        "patch_ids": comparison.patch_ids,
                        "patch_overlap": comparison.patch_overlap,
                        "missing_blob_commits": comparison.missing_blob_commits,
                        "changed_files": comparison.changed_files,
                        "conflict_estimate": comparison.conflict_estimate,
                    },
                    provenance={"method": "native-git", "version": "git-analysis-2026.07.1"},
                )
                self.session.add(evidence)
                completed += 1
                emit_event(
                    self.session,
                    analysis,
                    "structural.repository_persisted",
                    payload={"repository_id": str(repository.id), "completed": completed},
                )
                self.session.commit()
            except PlatformError as exc:
                warning = {
                    "code": exc.code,
                    "message": (
                        f"Structural analysis unavailable for {repository.owner}/{repository.name}"
                    ),
                    "repository_id": str(repository.id),
                }
                analysis.warnings = [*analysis.warnings, warning]
                emit_event(self.session, analysis, "structural.repository_failed", payload=warning)
                self.session.commit()
        analysis.sampling = {
            **analysis.sampling,
            "deep_repository_cap": self.settings.max_deep_repositories,
            "deep_repositories_selected": len(snapshots),
            "deep_repositories_analyzed": completed,
        }
        self._finish_stage(analysis, "structural", {"repositories_analyzed": completed})

    def _score_and_classify(self, analysis: AnalysisRun) -> None:
        if self._stage_complete(analysis, "scoring"):
            return
        self._stage(analysis, "scoring", 0.75)
        snapshots = self.session.scalars(
            select(RepositorySnapshot).where(RepositorySnapshot.analysis_id == analysis.id)
        ).all()
        for snapshot in snapshots:
            metrics = {**_metadata_metrics(snapshot.raw_metadata), **snapshot.metrics}
            snapshot.metrics = metrics
            self.session.execute(
                delete(ScoreSnapshot).where(
                    ScoreSnapshot.analysis_id == analysis.id,
                    ScoreSnapshot.repository_id == snapshot.repository_id,
                )
            )
            for score in calculate_scores(metrics):
                self.session.add(
                    ScoreSnapshot(
                        analysis_id=analysis.id,
                        repository_id=snapshot.repository_id,
                        dimension=score.dimension,
                        value=score.value,
                        confidence=score.confidence,
                        raw_inputs=score.raw_inputs,
                        available_inputs=score.available_inputs,
                        missing_inputs=score.missing_inputs,
                        depth=snapshot.depth,
                        version=score.version,
                    )
                )
            classification = classify_repository(metrics)
            evidence_ids = [
                str(identifier)
                for identifier in self.session.scalars(
                    select(EvidenceItem.id).where(
                        EvidenceItem.analysis_id == analysis.id,
                        EvidenceItem.repository_id == snapshot.repository_id,
                    )
                ).all()
            ]
            existing = self.session.scalar(
                select(Classification).where(
                    Classification.analysis_id == analysis.id,
                    Classification.repository_id == snapshot.repository_id,
                )
            )
            values = {
                "label": classification.label,
                "confidence": classification.confidence,
                "reasons": classification.reasons,
                "evidence_ids": evidence_ids,
                "missing_inputs": classification.missing_inputs,
                "version": classification.version,
            }
            if existing is None:
                self.session.add(
                    Classification(
                        analysis_id=analysis.id, repository_id=snapshot.repository_id, **values
                    )
                )
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
        self._finish_stage(analysis, "scoring", {"repositories_scored": len(snapshots)})

    def _cluster(self, analysis: AnalysisRun) -> None:
        if self._stage_complete(analysis, "clustering"):
            return
        self._stage(analysis, "clustering", 0.88)
        self.session.execute(
            delete(ClusterMember).where(
                ClusterMember.cluster_id.in_(
                    select(DevelopmentCluster.id).where(
                        DevelopmentCluster.analysis_id == analysis.id
                    )
                )
            )
        )
        self.session.execute(
            delete(DevelopmentCluster).where(DevelopmentCluster.analysis_id == analysis.id)
        )
        root = self._root_repository(analysis)
        snapshots = self.session.scalars(
            select(RepositorySnapshot).where(
                RepositorySnapshot.analysis_id == analysis.id,
                RepositorySnapshot.shortlisted.is_(True),
                RepositorySnapshot.repository_id != root.id,
            )
        ).all()
        vectors = [
            build_vector(
                str(snapshot.repository_id),
                {
                    "changed_paths": snapshot.metrics.get("changed_paths", []),
                    "dependencies_added": snapshot.metrics.get("dependencies_added", []),
                    "commit_terms": snapshot.raw_metadata.get("topics", []),
                },
            )
            for snapshot in snapshots
        ]
        clusters = cluster_vectors(vectors)
        for result in clusters:
            cluster = DevelopmentCluster(
                analysis_id=analysis.id,
                label=result.label,
                summary=(
                    "Heuristic direction represented by "
                    f"{', '.join(result.shared_tokens) or 'limited shared evidence'}."
                ),
                feature_vector={"representative_tokens": result.shared_tokens},
                representative_evidence_ids=[],
                algorithm=result.algorithm,
                labeling_method=result.labeling_method,
                confidence=result.confidence,
            )
            self.session.add(cluster)
            self.session.flush()
            for repository_id in result.members:
                self.session.add(
                    ClusterMember(
                        cluster_id=cluster.id,
                        repository_id=uuid.UUID(repository_id),
                        similarity=result.confidence,
                    )
                )
        self._finish_stage(analysis, "clustering", {"clusters": len(clusters)})

    def _stage(self, analysis: AnalysisRun, stage: str, progress: float) -> None:
        self._check_cancelled(analysis)
        analysis.stage = stage
        analysis.progress = progress
        checkpoint = self.session.scalar(
            select(StageCheckpoint).where(
                StageCheckpoint.analysis_id == analysis.id, StageCheckpoint.stage == stage
            )
        )
        if checkpoint is None:
            checkpoint = StageCheckpoint(
                analysis_id=analysis.id, stage=stage, status="running", attempts=1
            )
            self.session.add(checkpoint)
        else:
            checkpoint.status = "running"
            checkpoint.attempts += 1
            checkpoint.error = None
        emit_event(self.session, analysis, "stage.started", stage=stage, progress=progress)
        self.session.commit()

    def _finish_stage(self, analysis: AnalysisRun, stage: str, cursor: dict[str, Any]) -> None:
        checkpoint = self.session.scalar(
            select(StageCheckpoint).where(
                StageCheckpoint.analysis_id == analysis.id, StageCheckpoint.stage == stage
            )
        )
        if checkpoint is not None:
            checkpoint.status = "completed"
            checkpoint.cursor = cursor
        emit_event(self.session, analysis, "stage.completed", stage=stage, payload=cursor)
        self.session.commit()

    def _stage_complete(self, analysis: AnalysisRun, stage: str) -> bool:
        return (
            self.session.scalar(
                select(StageCheckpoint.status).where(
                    StageCheckpoint.analysis_id == analysis.id, StageCheckpoint.stage == stage
                )
            )
            == "completed"
        )

    def _check_cancelled(self, analysis: AnalysisRun) -> None:
        self.session.refresh(analysis)
        if analysis.cancel_requested:
            raise AnalysisCancelled
        if analysis.started_at is not None:
            elapsed = (datetime.now(UTC) - analysis.started_at).total_seconds()
            if elapsed > self.settings.max_analysis_seconds:
                raise PlatformError(
                    "analysis_deadline_exceeded",
                    "Analysis exceeded its configured hard deadline",
                    status_code=504,
                )

    def _remaining_analysis_seconds(self, analysis: AnalysisRun) -> float:
        if analysis.started_at is None:
            return float(self.settings.max_analysis_seconds)
        elapsed = (datetime.now(UTC) - analysis.started_at).total_seconds()
        remaining = self.settings.max_analysis_seconds - elapsed
        if remaining <= 0:
            raise PlatformError(
                "analysis_deadline_exceeded",
                "Analysis exceeded its configured hard deadline",
                status_code=504,
            )
        return remaining

    def _upsert_repository(self, data: dict[str, Any], network_id: uuid.UUID | None) -> Repository:
        repository = self.session.scalar(
            select(Repository).where(Repository.github_id == data["github_id"])
        )
        values = {
            "network_id": network_id,
            "owner": data["owner"],
            "name": data["name"],
            "html_url": data["html_url"],
            "clone_url": data["clone_url"],
            "default_branch": data["default_branch"],
            "is_fork": data["is_fork"],
            "archived": data["archived"],
            "disabled": data["disabled"],
            "metadata_json": data,
        }
        if repository is None:
            repository = Repository(github_id=data["github_id"], **values)
            self.session.add(repository)
            self.session.flush()
        else:
            for key, value in values.items():
                setattr(repository, key, value)
        return repository

    def _upsert_snapshot(
        self, analysis_id: uuid.UUID, repository: Repository, data: dict[str, Any]
    ) -> RepositorySnapshot:
        snapshot = self.session.scalar(
            select(RepositorySnapshot).where(
                RepositorySnapshot.analysis_id == analysis_id,
                RepositorySnapshot.repository_id == repository.id,
            )
        )
        if snapshot is None:
            snapshot = RepositorySnapshot(
                analysis_id=analysis_id,
                repository_id=repository.id,
                raw_metadata=data,
                metrics=_metadata_metrics(data),
                provenance={
                    "source": "github_rest",
                    "api_version": self.settings.github_api_version,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                },
            )
            self.session.add(snapshot)
        else:
            snapshot.raw_metadata = data
        return snapshot

    def _upsert_branch(
        self,
        analysis_id: uuid.UUID,
        repository: Repository,
        data: dict[str, Any],
        included: bool,
    ) -> None:
        branch = self.session.scalar(
            select(Branch).where(
                Branch.analysis_id == analysis_id,
                Branch.repository_id == repository.id,
                Branch.name == data["name"],
            )
        )
        if branch is None:
            self.session.add(
                Branch(
                    analysis_id=analysis_id,
                    repository_id=repository.id,
                    name=data["name"],
                    head_sha=data["head_sha"],
                    is_default=True,
                    included=included,
                    selection_reason="default_branch",
                    analysis_priority=100,
                )
            )
        else:
            branch.head_sha = data["head_sha"]
            branch.included = included

    def _root_repository(self, analysis: AnalysisRun) -> Repository:
        network = self.session.get(RepositoryNetwork, analysis.network_id)
        if network is None or network.root_repository_id is None:
            raise PlatformError(
                "network_not_resolved", "Repository network is not resolved", status_code=409
            )
        repository = self.session.get(Repository, network.root_repository_id)
        if repository is None:
            raise PlatformError(
                "root_not_found", "Network root repository is missing", status_code=500
            )
        return repository


def _metadata_metrics(data: dict[str, Any]) -> dict[str, Any]:
    pushed = data.get("pushed_at")
    days_since_push: int | None = None
    if pushed:
        try:
            parsed = datetime.fromisoformat(str(pushed).replace("Z", "+00:00"))
            days_since_push = max(0, (datetime.now(UTC) - parsed).days)
        except ValueError:
            pass
    return {
        "stars": int(data.get("stars") or 0),
        "forks": int(data.get("forks") or 0),
        "watchers": int(data.get("watchers") or 0),
        "days_since_push": days_since_push,
    }
