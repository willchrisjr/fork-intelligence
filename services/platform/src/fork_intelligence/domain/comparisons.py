from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fork_intelligence.domain.files import FILE_CATEGORIES


@dataclass(frozen=True, slots=True)
class ComparisonRepository:
    repository_id: str
    full_name: str
    role: str
    default_branch: str
    head_sha: str | None
    metrics: dict[str, Any]


def build_comparison_result(repositories: list[ComparisonRepository]) -> dict[str, Any]:
    identities = [
        {
            "repository_id": repository.repository_id,
            "full_name": repository.full_name,
            "role": repository.role,
            "default_branch": repository.default_branch,
            "head_sha": repository.head_sha,
        }
        for repository in repositories
    ]
    composition = [
        {
            "repository_id": repository.repository_id,
            "full_name": repository.full_name,
            "categories": {
                category: int((repository.metrics.get("file_composition") or {}).get(category, 0))
                for category in FILE_CATEGORIES
            },
        }
        for repository in repositories
    ]
    pairs: list[dict[str, Any]] = []
    overlap: list[dict[str, Any]] = []
    integration: list[dict[str, Any]] = []
    for index, left in enumerate(repositories):
        for right in repositories[index + 1 :]:
            left_paths = set(left.metrics.get("changed_paths", []))
            right_paths = set(right.metrics.get("changed_paths", []))
            shared_paths = sorted(left_paths & right_paths)
            path_union = left_paths | right_paths
            path_overlap = round(len(shared_paths) / (len(path_union) or 1), 3)
            left_patches = set(left.metrics.get("patch_fingerprints", []))
            right_patches = set(right.metrics.get("patch_fingerprints", []))
            shared_patches = sorted(left_patches & right_patches)
            left_aggregate = left.metrics.get("aggregate_patch_id")
            right_aggregate = right.metrics.get("aggregate_patch_id")
            aggregate_match = bool(
                left_aggregate and right_aggregate and left_aggregate == right_aggregate
            )
            patch_overlap = {
                "shared_patch_ids": shared_patches,
                "shared_patch_count": len(shared_patches),
                "aggregate_match": aggregate_match,
                "method": "stable-patch-id-and-range-patch-id-v1",
            }
            integration_row = {
                "left_repository_id": left.repository_id,
                "right_repository_id": right.repository_id,
                "estimate": _integration_estimate(
                    shared_path_count=len(shared_paths),
                    path_overlap=path_overlap,
                    shared_patch_count=len(shared_patches),
                    aggregate_match=aggregate_match,
                ),
                "shared_path_count": len(shared_paths),
                "path_overlap": path_overlap,
                "method": "changed-path-and-patch-overlap-v1",
                "disclosure": "approximation_not_merge_simulation",
            }
            pair = {
                "left_repository_id": left.repository_id,
                "right_repository_id": right.repository_id,
                "shared_changed_paths": shared_paths,
                "path_overlap": path_overlap,
                "patch_overlap": patch_overlap,
                "metrics": {"left": left.metrics, "right": right.metrics},
                "integration_complexity": integration_row,
            }
            pairs.append(pair)
            overlap.append(
                {
                    "left_repository_id": left.repository_id,
                    "right_repository_id": right.repository_id,
                    "shared_changed_paths": shared_paths,
                    "path_overlap": path_overlap,
                    **patch_overlap,
                }
            )
            integration.append(integration_row)
    return {
        "repositories": identities,
        "overlap": overlap,
        "composition": composition,
        "integration": integration,
        "pairs": pairs,
    }


def _integration_estimate(
    *,
    shared_path_count: int,
    path_overlap: float,
    shared_patch_count: int,
    aggregate_match: bool,
) -> str:
    if aggregate_match or shared_patch_count > 0:
        return "lower"
    if shared_path_count > 20 or path_overlap >= 0.5:
        return "high"
    if shared_path_count > 0:
        return "moderate"
    return "bounded"
