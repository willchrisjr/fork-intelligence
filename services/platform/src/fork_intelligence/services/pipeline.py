from __future__ import annotations

import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from fork_intelligence.adapters.credential_router import (
    COVERAGE_LIMITATION,
    GitHubCredentialRouter,
)
from fork_intelligence.adapters.git import BareNetworkStore
from fork_intelligence.config import Settings, get_settings
from fork_intelligence.domain.branch_planning import (
    BRANCH_PLANNER_VERSION,
    BranchPlan,
    BranchSignal,
    plan_branches,
)
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
from fork_intelligence.services.persistence import (
    BranchCandidate,
    record_branch_plan,
    record_credential_mode_transition,
)

# Provider conditions that leave committed evidence intact and the run
# resumable, rather than failing it. Both mean the router ran out of usable
# access modes: its quota is spent, or every configured credential was refused.
PROVIDER_EXHAUSTED_CODES = frozenset({"github_rate_limited", "github_unauthorized"})


class AnalysisCancelled(Exception):
    pass


def _as_utc(value: datetime) -> datetime:
    """Treat a stored timestamp as UTC.

    Timestamp columns are ``DateTime(timezone=True)`` and every writer uses
    ``datetime.now(UTC)``, so a naive value can only come from a driver that
    drops the offset on read. Normalizing keeps deadline arithmetic from
    raising a TypeError that would misreport the underlying condition.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class AnalysisPipeline:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        github: GitHubCredentialRouter | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.github = github or GitHubCredentialRouter(self.settings)
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
                self._plan_branches(analysis)
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
            if exc.code not in PROVIDER_EXHAUSTED_CODES:
                self.session.rollback()
                analysis = require_analysis(self.session, analysis_id)
                # A failure unrelated to provider capacity must still not lose a
                # fallback that already happened; the reduced coverage is part
                # of how this analysis got where it did.
                self._sync_access_provenance(analysis)
                analysis.status = "failed"
                analysis.error = {"code": exc.code, "message": exc.message}
                emit_event(self.session, analysis, "analysis.failed", payload=analysis.error)
                self.session.commit()
                raise
            # Reaching here means the router already exhausted every access mode
            # it had: the credential fell back to anonymous, or none was
            # configured, and public access is blocked too. Committed evidence
            # stays untouched and the run is left resumable.
            self.session.rollback()
            analysis = require_analysis(self.session, analysis_id)
            self._sync_access_provenance(analysis)
            quota_exhausted = exc.code == "github_rate_limited"
            resolution = (
                "Resume after the documented quota reset"
                if quota_exhausted
                else "Resume once provider access is restored"
            )
            analysis.status = "partial"
            analysis.stage = "waiting_for_quota" if quota_exhausted else "waiting_for_provider"
            # The quota is taken from the router's sanitized snapshot rather
            # than the raw error details, so only known provider fields reach a
            # record that is persisted, exported, and rendered in the browser.
            quota = self.github.quota_snapshot
            analysis.error = {
                "code": exc.code,
                "message": f"GitHub access could not continue. {resolution}",
                "quota": quota,
                "credential_mode": analysis.credential_mode,
            }
            warning = {
                "code": "provider_access_exhausted",
                "message": (
                    "Partial evidence is preserved; no remaining GitHub access mode could "
                    f"continue. {resolution}"
                ),
                "credential_mode": analysis.credential_mode,
                "quota": quota,
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
        # Captured per fetch: the router only remembers its latest call.
        requested_provenance = self._provider_provenance(self._router_field_provenance())
        source = requested_data.get("source")
        root_data = requested_data
        root_provenance = requested_provenance
        if source and source["full_name"].lower() != requested_data["full_name"].lower():
            source_identifier = parse_repository_identifier(source["full_name"])
            root_data = self.github.get_repository(source_identifier.owner, source_identifier.name)
            root_provenance = self._provider_provenance(self._router_field_provenance())

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
        self._upsert_snapshot(analysis.id, root, root_data, root_provenance)
        self._upsert_snapshot(analysis.id, requested, requested_data, requested_provenance)
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
        if self.github.credential_mode != "authenticated":
            request_budget = min(request_budget, 45)
        capped = False
        page_cap_reached = False
        requests_used = 0
        census_start_mode = self.github.credential_mode
        discovered_before_downgrade: int | None = None
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
                    # Fork pages come from REST pagination, never the GraphQL
                    # accelerator, so this snapshot is attributed to REST alone.
                    self._upsert_snapshot(
                        analysis.id, repository, item, self._provider_provenance()
                    )
                    seen.add(repository.github_id)
                    queue.append(repository)
                if (
                    discovered_before_downgrade is None
                    and self.github.credential_mode != census_start_mode
                ):
                    discovered_before_downgrade = len(seen) - 1
                self._sync_access_provenance(analysis)
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
        credential_mode_changed = self.github.credential_mode != census_start_mode
        analysis.sampling = {
            "expected_network_size": int(root.metadata_json.get("forks") or 0) + 1,
            "accessible_forks": len(seen) - 1,
            "fork_cap": max_forks,
            "forks_capped": capped,
            "github_page_cap": self.settings.max_github_pages,
            "github_request_cap": request_budget,
            "github_request_cap_authenticated": self.github.credential_mode == "authenticated",
            "credential_mode": self.github.credential_mode,
            "credential_mode_changed_during_census": credential_mode_changed,
            "nested_traversal_incomplete": traversal_incomplete,
            "github_page_cap_reached": page_cap_reached,
            "incomplete_reasons": [
                reason
                for condition, reason in (
                    (capped, "fork_cap_reached"),
                    (traversal_incomplete, "github_request_budget_reached"),
                    (page_cap_reached, "github_page_cap_reached"),
                    (credential_mode_changed, "credential_mode_downgraded"),
                )
                if condition
            ],
        }
        if credential_mode_changed:
            # AC-RA-AGA-003.2: name the scope a mid-census downgrade affected,
            # since forks listed before it were drawn under a wider budget.
            analysis.warnings = [
                *analysis.warnings,
                {
                    "code": "credential_mode_downgraded",
                    "message": (
                        "Authenticated GitHub access became unavailable during the fork "
                        "census; remaining discovery used anonymous access"
                    ),
                    "credential_mode": self.github.credential_mode,
                    "repositories_discovered_before_downgrade": discovered_before_downgrade,
                },
            ]
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
        branches_analyzed = 0
        non_default_analyzed = 0
        for snapshot in snapshots:
            self._check_cancelled(analysis)
            repository = self.session.get(Repository, snapshot.repository_id)
            if repository is None or repository.disabled:
                continue
            # Analyze only the exact heads the plan selected, never a ref
            # discovered implicitly at fetch time (Repository Evidence
            # Acquisition: selection provenance stays explicit).
            selected = self._selected_branches(analysis.id, repository.id)
            if not selected:
                continue
            try:
                repository_branches = 0
                for branch_entry in selected:
                    headline = branch_entry.is_default or repository_branches == 0
                    comparison = self._analyze_selected_branch(
                        analysis, store, root_ref, repository, snapshot, branch_entry, headline
                    )
                    if comparison is None:
                        continue
                    repository_branches += 1
                    branches_analyzed += 1
                    if not branch_entry.is_default:
                        non_default_analyzed += 1
                    self.session.commit()
                if repository_branches:
                    completed += 1
                    emit_event(
                        self.session,
                        analysis,
                        "structural.repository_persisted",
                        payload={
                            "repository_id": str(repository.id),
                            "completed": completed,
                            "branches_analyzed": repository_branches,
                        },
                    )
                    self.session.commit()
            except PlatformError as exc:
                # Provider exhaustion is not specific to this repository -- it
                # will block every remaining one too. Let it reach the run-level
                # handler so the analysis is preserved as partial instead of
                # completing with an empty structural stage.
                if isinstance(exc, GitHubError) and exc.code in PROVIDER_EXHAUSTED_CODES:
                    raise
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
            # AC-RA-RBP-004.1: branch-level coverage, distinct from repo counts.
            "branches_structurally_analyzed": branches_analyzed,
            # AC-RA-RBP-004.3: make it explicit when coverage never left the
            # default branch, so a reader does not assume broader coverage.
            "structural_coverage_default_only": non_default_analyzed == 0,
        }
        self._finish_stage(
            analysis,
            "structural",
            {"repositories_analyzed": completed, "branches_analyzed": branches_analyzed},
        )

    def _analyze_selected_branch(
        self,
        analysis: AnalysisRun,
        store: BareNetworkStore,
        root_ref: str,
        repository: Repository,
        snapshot: RepositorySnapshot,
        branch_entry: Branch,
        headline: bool,
    ) -> object | None:
        """Fetch one selected head and compare it against the root default.

        The headline branch drives the repository's snapshot metrics, preserving
        the scoring inputs the rest of the pipeline expects. Additional selected
        branches contribute their own evidence item and branch-coverage count
        without disturbing those inputs.
        """
        if not branch_entry.head_sha:
            return None
        fork_ref = store.fetch_branch(
            str(analysis.id),
            repository.github_id,
            repository.owner,
            repository.name,
            branch_entry.name,
            branch_entry.head_sha,
        )
        comparison = store.compare(
            root_ref, fork_ref, timeout=self._remaining_analysis_seconds(analysis)
        )
        changed_paths = [item["path"] for item in comparison.changed_files]
        if headline:
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
            source_url=(
                f"{repository.html_url}/compare/{comparison.merge_base}...{branch_entry.head_sha}"
            ),
            payload={
                "branch": branch_entry.name,
                "is_default": branch_entry.is_default,
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
        return comparison

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

    def _provider_provenance(
        self, field_provenance: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Provenance for one metadata snapshot.

        Field attribution is passed in rather than read from the router here.
        The router only remembers its most recent ``get_repository`` call, so
        reading it at persistence time would stamp fork snapshots -- collected
        by REST fork pagination -- with the root repository's attribution, and
        credit GraphQL for data it never supplied.
        """
        provenance: dict[str, Any] = {
            "source": "github_rest",
            "api_version": self.settings.github_api_version,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "credential_mode": self.github.credential_mode,
        }
        if field_provenance:
            provenance |= field_provenance
        return provenance

    def _router_field_provenance(self) -> dict[str, Any] | None:
        """Field attribution for the repository just fetched, if the router reports it.

        Must be called immediately after the corresponding ``get_repository``:
        a later call overwrites it.
        """
        value = getattr(self.github, "last_repository_provenance", None)
        return value if isinstance(value, dict) and value else None

    def _sync_access_provenance(self, analysis: AnalysisRun) -> None:
        """Fold the router's access state into the analysis record.

        Called wherever the pipeline is about to commit, so the effective
        credential mode and remaining provider quota stay observable while
        metadata is still being collected rather than only at completion.
        """
        for transition in self.github.drain_transitions():
            record_credential_mode_transition(
                self.session,
                analysis,
                to_mode=transition.to_mode,
                reason=transition.reason,
                coverage_limitation=transition.coverage_limitation,
            )
        # A resumed run gets a fresh router, which re-probes the credential and
        # may legitimately come back on a different mode than the one the
        # previous attempt persisted. Reconcile so the stored mode always names
        # the access actually in use rather than a stale earlier verdict.
        if self.github.credential_mode != analysis.credential_mode:
            record_credential_mode_transition(
                self.session,
                analysis,
                to_mode=self.github.credential_mode,
                reason="provider_access_revalidated_on_resume",
                coverage_limitation=(
                    None if self.github.credential_mode == "authenticated" else COVERAGE_LIMITATION
                ),
            )
        quota = self.github.quota_snapshot
        if quota:
            analysis.quota_snapshot = quota

    def _stage(self, analysis: AnalysisRun, stage: str, progress: float) -> None:
        self._check_cancelled(analysis)
        analysis.stage = stage
        analysis.progress = progress
        self._sync_access_provenance(analysis)
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
        self._sync_access_provenance(analysis)
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
            elapsed = (datetime.now(UTC) - _as_utc(analysis.started_at)).total_seconds()
            if elapsed > self.settings.max_analysis_seconds:
                raise PlatformError(
                    "analysis_deadline_exceeded",
                    "Analysis exceeded its configured hard deadline",
                    status_code=504,
                )

    def _remaining_analysis_seconds(self, analysis: AnalysisRun) -> float:
        if analysis.started_at is None:
            return float(self.settings.max_analysis_seconds)
        elapsed = (datetime.now(UTC) - _as_utc(analysis.started_at)).total_seconds()
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
        self,
        analysis_id: uuid.UUID,
        repository: Repository,
        data: dict[str, Any],
        provenance: dict[str, Any] | None = None,
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
                provenance=provenance or self._provider_provenance(),
            )
            self.session.add(snapshot)
        else:
            snapshot.raw_metadata = data
            # Refresh attribution alongside the data it describes; leaving the
            # original would let a resumed run describe this collection with
            # the previous attempt's transports and errors.
            snapshot.provenance = provenance or self._provider_provenance()
        return snapshot

    def _record_branch_plan(
        self,
        analysis_id: uuid.UUID,
        repository: Repository,
        plan: BranchPlan,
        retrieval_time: datetime,
    ) -> None:
        """Persist every considered candidate through the WO-1 recorder.

        The recorder and schema are reused unchanged: this stage only decides,
        it does not own persistence. All decisions -- selected, excluded, and
        unevaluated -- are written so the plan is fully inspectable.
        """
        record_branch_plan(
            self.session,
            analysis_id,
            repository.id,
            [
                BranchCandidate(
                    name=entry.name,
                    is_default=entry.is_default,
                    priority=entry.priority,
                    decision=entry.decision,
                    selection_reason=entry.selection_reason,
                    # Observed fields are required for a decided candidate; an
                    # unevaluated one still carries the head we enumerated.
                    head_sha=entry.head_sha or None,
                    retrieval_time=retrieval_time if entry.decision != "unevaluated" else None,
                )
                for entry in plan.entries
            ],
            planner_version=BRANCH_PLANNER_VERSION,
        )

    def _plan_branches(self, analysis: AnalysisRun) -> None:
        """Deterministically plan branches for the root and shortlisted forks.

        Enumerates candidates, establishes ranking signals through a bounded
        per-repository probe, and delegates the decision to the pure planner.
        Candidates past the probe budget are left unevaluated with the missing
        input named rather than guessed at (AC-RA-RBP-002.3).
        """
        if self._stage_complete(analysis, "branch_planning"):
            # A completed checkpoint is reusable only where its observed heads
            # and selection inputs are still current (AC-RA-RBP-003.3).
            self._revalidate_branch_plans(analysis)
            return
        self._stage(analysis, "branch_planning", 0.40)
        cap = self.settings.max_branches_per_fork
        totals = {"considered": 0, "selected": 0, "excluded": 0, "unevaluated": 0}

        for repository in self._planned_repositories(analysis):
            self._check_cancelled(analysis)
            plan = self._plan_repository(analysis, repository, cap)
            totals["considered"] += plan.considered
            totals["selected"] += plan.selected
            totals["excluded"] += plan.excluded
            totals["unevaluated"] += plan.unevaluated

        analysis.sampling = {
            **analysis.sampling,
            "branch_cap": cap,
            "branch_planner_version": BRANCH_PLANNER_VERSION,
            "branches_considered": totals["considered"],
            "branches_selected": totals["selected"],
            # AC-RA-RBP-004.2: cap exclusions and unevaluable candidates are
            # reported separately so sampling choices are never confused with
            # provider or repository failures.
            "branches_excluded_by_cap": totals["excluded"],
            "branches_unevaluated": totals["unevaluated"],
        }
        self._finish_stage(analysis, "branch_planning", totals)

    def _plan_repository(
        self, analysis: AnalysisRun, repository: Repository, cap: int
    ) -> BranchPlan:
        """Plan one repository and persist the result."""
        retrieval_time = datetime.now(UTC)
        signals = self._branch_signals(repository)
        plan = plan_branches(signals, cap=cap)
        self._record_branch_plan(analysis.id, repository, plan, retrieval_time)
        emit_event(
            self.session,
            analysis,
            "branch_planning.repository_planned",
            payload={
                "repository_id": str(repository.id),
                "selected": plan.selected,
                "excluded": plan.excluded,
                "unevaluated": plan.unevaluated,
            },
        )
        self.session.commit()
        return plan

    def _revalidate_branch_plans(self, analysis: AnalysisRun) -> None:
        """Re-check a checkpointed branch plan before a resumed run reuses it.

        Only repositories whose observed heads or selection inputs moved are
        re-planned; everything else keeps its sealed plan and its committed
        evidence. When the provider cannot be reached the existing plan is
        preserved and reported as unvalidated rather than silently trusted or
        needlessly discarded.
        """
        cap = self.settings.max_branches_per_fork
        sampling = analysis.sampling or {}
        # A changed cap or planner version changes the selection inputs for
        # every repository, so nothing from the old plan can be reused.
        inputs_changed = (
            _optional_int(sampling.get("branch_cap")) != cap
            or sampling.get("branch_planner_version") != BRANCH_PLANNER_VERSION
        )

        reused: list[str] = []
        replanned: list[dict[str, Any]] = []
        unvalidated: list[dict[str, Any]] = []

        for repository in self._planned_repositories(analysis):
            self._check_cancelled(analysis)
            cause: str | None = "selection_inputs_changed" if inputs_changed else None
            if cause is None:
                cause = self._branch_plan_invalidation(repository, analysis)
            if cause is None:
                reused.append(str(repository.id))
                continue
            if cause == "provider_unavailable":
                # Preserved, but the caller must not read this as "confirmed
                # current" (AC-RA-003.2).
                unvalidated.append({"repository_id": str(repository.id), "cause": cause})
                continue
            self._plan_repository(analysis, repository, cap)
            replanned.append({"repository_id": str(repository.id), "cause": cause})

        summary = {
            "revalidated_at": datetime.now(UTC).isoformat(),
            "reused": len(reused),
            "replanned": len(replanned),
            "unvalidated": len(unvalidated),
            "replanned_repositories": replanned,
            "unvalidated_repositories": unvalidated,
        }
        analysis.sampling = {
            **analysis.sampling,
            "branch_cap": cap,
            "branch_planner_version": BRANCH_PLANNER_VERSION,
            "branch_plan_revalidation": summary,
        }
        if unvalidated:
            analysis.warnings = [
                *analysis.warnings,
                {
                    "code": "branch_plan_unvalidated",
                    "message": (
                        "Branch plans for some repositories could not be re-validated "
                        "against the provider on resume and were reused as-is"
                    ),
                    "affected_scope": "branch_plan_revalidation",
                    "repositories": len(unvalidated),
                },
            ]
        emit_event(
            self.session,
            analysis,
            "branch_planning.revalidated",
            stage="branch_planning",
            payload=summary,
        )
        checkpoint = self.session.scalar(
            select(StageCheckpoint).where(
                StageCheckpoint.analysis_id == analysis.id,
                StageCheckpoint.stage == "branch_planning",
            )
        )
        if checkpoint is not None:
            checkpoint.cursor = {**(checkpoint.cursor or {}), "revalidation": summary}
        self.session.commit()

    def _branch_plan_invalidation(
        self, repository: Repository, analysis: AnalysisRun
    ) -> str | None:
        """Name why this repository's plan cannot be reused, or None if it can.

        Compares the heads the plan observed against the provider's current
        heads. Only the selected candidates matter: those are the refs the
        structural stage will fetch, so a moved head there would make the
        analysis cite a state it never actually examined.
        """
        planned = self._selected_branches(analysis.id, repository.id)
        if not planned:
            return "no_plan_for_current_version"
        try:
            current = {
                branch["name"]: branch["head_sha"]
                for branch in self.github.list_branches(
                    repository.owner,
                    repository.name,
                    max_branches=self.settings.max_branch_candidates,
                )
            }
        except GitHubError as exc:
            if exc.code in PROVIDER_EXHAUSTED_CODES:
                raise
            return "provider_unavailable"
        for entry in planned:
            observed = current.get(entry.name)
            if observed is None:
                return "branch_disappeared"
            if entry.head_sha and observed != entry.head_sha:
                return "head_moved"
        return None

    def _planned_repositories(self, analysis: AnalysisRun) -> list[Repository]:
        """The root plus shortlisted forks, the repositories structural fetch covers."""
        root = self._root_repository(analysis)
        forks = self.session.scalars(
            select(Repository)
            .join(RepositorySnapshot, RepositorySnapshot.repository_id == Repository.id)
            .where(
                RepositorySnapshot.analysis_id == analysis.id,
                RepositorySnapshot.shortlisted.is_(True),
                RepositorySnapshot.repository_id != root.id,
                Repository.disabled.is_(False),
            )
            .order_by(Repository.github_id, Repository.id)
            .limit(self.settings.max_deep_repositories)
        ).all()
        return [root, *forks]

    def _branch_signals(self, repository: Repository) -> list[BranchSignal]:
        """Enumerate branch candidates and probe ranking signals within budget."""
        try:
            branches = self.github.list_branches(
                repository.owner,
                repository.name,
                max_branches=self.settings.max_branch_candidates,
            )
        except GitHubError as exc:
            if exc.code in PROVIDER_EXHAUSTED_CODES:
                raise
            # Enumeration failed for a repository-specific reason. The default
            # branch is still known from metadata, so plan it alone rather than
            # abandoning the repository (AC-RA-RBP-001.5).
            branches = []

        default_name = repository.default_branch
        signals: list[BranchSignal] = []
        seen_default = False
        probes_remaining = self.settings.max_branch_probes

        for branch in branches:
            is_default = branch["name"] == default_name
            if is_default:
                seen_default = True
                signals.append(
                    BranchSignal(
                        name=branch["name"],
                        head_sha=branch["head_sha"],
                        is_default=True,
                    )
                )
                continue
            if probes_remaining > 0:
                probes_remaining -= 1
                signals.append(self._probe_branch(repository, default_name, branch))
            else:
                signals.append(
                    BranchSignal(
                        name=branch["name"],
                        head_sha=branch["head_sha"],
                        is_default=False,
                        missing_input="probe_budget_exhausted",
                    )
                )

        if not seen_default:
            # Guarantee the default is always a candidate even when enumeration
            # was empty or omitted it, so AC-RA-RBP-001.2 always holds. Its head
            # is resolved directly when the listing did not include it.
            try:
                default = self.github.get_branch(repository.owner, repository.name, default_name)
            except GitHubError as exc:
                if exc.code in PROVIDER_EXHAUSTED_CODES:
                    raise
                default = None
            if default and default.get("head_sha"):
                signals.append(
                    BranchSignal(name=default_name, head_sha=default["head_sha"], is_default=True)
                )
        return signals

    def _probe_branch(
        self, repository: Repository, default_name: str, branch: dict[str, str]
    ) -> BranchSignal:
        """Establish ahead and activity signals for one candidate, or mark it unevaluable."""
        try:
            comparison = self.github.compare_commits(
                repository.owner, repository.name, default_name, branch["name"]
            )
        except GitHubError as exc:
            if exc.code in PROVIDER_EXHAUSTED_CODES:
                raise
            return BranchSignal(
                name=branch["name"],
                head_sha=branch["head_sha"],
                is_default=False,
                missing_input="relationship_probe_failed",
            )
        return BranchSignal(
            name=branch["name"],
            head_sha=branch["head_sha"],
            is_default=False,
            last_activity=_parse_activity(comparison.get("last_activity")),
            ahead=int(comparison.get("ahead") or 0),
        )

    def _selected_branches(self, analysis_id: uuid.UUID, repository_id: uuid.UUID) -> list[Branch]:
        """Selected branch entries for a repository under the current planner version."""
        return list(
            self.session.scalars(
                select(Branch)
                .where(
                    Branch.analysis_id == analysis_id,
                    Branch.repository_id == repository_id,
                    Branch.planner_version == BRANCH_PLANNER_VERSION,
                    Branch.decision == "selected",
                )
                .order_by(Branch.priority)
            )
        )

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


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _parse_activity(value: object) -> datetime | None:
    """Parse a provider commit timestamp into an aware datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


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
