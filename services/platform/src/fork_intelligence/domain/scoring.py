from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

SCORE_VERSION = "score-2026.07.1"

DIMENSION_INPUTS: dict[str, tuple[str, ...]] = {
    "popularity": ("stars", "forks", "watchers"),
    "recent_activity": ("days_since_push", "commits_90d"),
    "sustained_activity": ("active_months_12m", "commits_365d"),
    "maintenance": ("active_months_12m", "releases_365d", "contributors", "has_tests", "has_ci"),
    "original_development": ("unique_patches", "source_files_changed", "test_files_changed"),
    "divergence": ("ahead", "files_changed", "directories_changed", "dependency_changes"),
    "adoption": ("stars", "forks", "watchers", "contributors"),
    "upstream_compatibility": ("behind", "days_since_common_commit", "conflict_estimate"),
    "maintained_successor": (
        "active_months_12m",
        "releases_365d",
        "contributors",
        "stars",
        "forks",
        "watchers",
        "commits_365d",
        "unique_patches",
        "source_files_changed",
        "test_files_changed",
        "has_tests",
        "has_ci",
        "days_since_push",
        "ahead",
        "behind",
        "days_since_common_commit",
        "conflict_estimate",
    ),
    "unmerged_innovation": ("unique_patches", "source_files_changed", "patch_overlap_upstream"),
}


@dataclass(frozen=True, slots=True)
class Score:
    dimension: str
    value: float
    confidence: float
    available_inputs: list[str]
    missing_inputs: list[str]
    raw_inputs: dict[str, Any]
    version: str = SCORE_VERSION


def _bounded(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _log(value: float, scale: float) -> float:
    return min(1.0, math.log1p(max(0.0, value)) / math.log1p(scale))


def calculate_scores(metrics: dict[str, Any]) -> list[Score]:
    stars = float(metrics.get("stars", 0) or 0)
    forks = float(metrics.get("forks", 0) or 0)
    watchers = float(metrics.get("watchers", 0) or 0)
    days_push = float(metrics.get("days_since_push", 3650) or 0)
    commits_90 = float(metrics.get("commits_90d", 0) or 0)
    commits_365 = float(metrics.get("commits_365d", 0) or 0)
    months = float(metrics.get("active_months_12m", 0) or 0)
    releases = float(metrics.get("releases_365d", 0) or 0)
    contributors = float(metrics.get("contributors", 0) or 0)
    unique_patches = float(metrics.get("unique_patches", 0) or 0)
    source_files = float(metrics.get("source_files_changed", 0) or 0)
    tests = float(metrics.get("test_files_changed", 0) or 0)
    ahead = float(metrics.get("ahead", 0) or 0)
    behind = float(metrics.get("behind", 0) or 0)
    files = float(metrics.get("files_changed", 0) or 0)
    directories = float(metrics.get("directories_changed", 0) or 0)
    dependencies = float(metrics.get("dependency_changes", 0) or 0)
    conflict = float(metrics.get("conflict_estimate", 0.5) or 0)
    common_days = float(metrics.get("days_since_common_commit", 3650) or 0)
    patch_overlap = float(metrics.get("patch_overlap_upstream", 0) or 0)
    recency = math.exp(-days_push / 180)
    has_tests = 1.0 if metrics.get("has_tests") else 0.0
    has_ci = 1.0 if metrics.get("has_ci") else 0.0

    values: dict[str, float] = {
        "popularity": 100
        * (0.55 * _log(stars, 1000) + 0.3 * _log(forks, 300) + 0.15 * _log(watchers, 100)),
        "recent_activity": 100 * (0.55 * recency + 0.45 * _log(commits_90, 50)),
        "sustained_activity": 100 * (0.65 * min(months / 12, 1) + 0.35 * _log(commits_365, 200)),
        "maintenance": 100
        * (
            0.35 * min(months / 12, 1)
            + 0.2 * _log(releases, 12)
            + 0.2 * _log(contributors, 10)
            + 0.125 * has_tests
            + 0.125 * has_ci
        ),
        "original_development": 100
        * (
            0.55 * _log(unique_patches, 100)
            + 0.35 * _log(source_files, 150)
            + 0.1 * _log(tests, 50)
        ),
        "divergence": 100
        * (
            0.35 * _log(ahead, 200)
            + 0.3 * _log(files, 500)
            + 0.2 * _log(directories, 50)
            + 0.15 * _log(dependencies, 20)
        ),
        "adoption": 100
        * (
            0.45 * _log(stars, 1000)
            + 0.25 * _log(forks, 300)
            + 0.1 * _log(watchers, 100)
            + 0.2 * _log(contributors, 50)
        ),
        "upstream_compatibility": 100
        * (
            0.45 * math.exp(-behind / 50)
            + 0.3 * math.exp(-common_days / 365)
            + 0.25 * (1 - min(conflict, 1))
        ),
        "unmerged_innovation": 100
        * (
            0.6 * _log(unique_patches, 100)
            + 0.3 * _log(source_files, 150)
            + 0.1 * (1 - min(patch_overlap, 1))
        ),
    }
    releases_score = 100 * _log(releases, 12)
    contributor_breadth_score = 100 * _log(contributors, 10)
    staleness_penalty = min(25.0, max(0.0, days_push - 365) / 365 * 12.5)
    divergence_penalty = min(20.0, 20 * _log(ahead, 200)) if months < 2 and ahead >= 20 else 0.0
    values["maintained_successor"] = (
        0.30 * values["maintenance"]
        + 0.15 * values["sustained_activity"]
        + 0.15 * values["adoption"]
        + 0.15 * values["original_development"]
        + 0.10 * releases_score
        + 0.10 * contributor_breadth_score
        + 0.05 * values["upstream_compatibility"]
        - staleness_penalty
        - divergence_penalty
    )
    results: list[Score] = []
    for dimension, value in values.items():
        expected = DIMENSION_INPUTS[dimension]
        available = [name for name in expected if name in metrics and metrics[name] is not None]
        missing = [name for name in expected if name not in available]
        confidence = round(len(available) / len(expected), 3)
        raw_inputs = {name: metrics[name] for name in available}
        if dimension == "maintained_successor":
            raw_inputs["profile_formula"] = {
                "maintenance": 0.30,
                "sustained_activity": 0.15,
                "adoption": 0.15,
                "original_development": 0.15,
                "releases": 0.10,
                "contributor_breadth": 0.10,
                "upstream_sync": 0.05,
            }
            raw_inputs["penalties"] = {
                "staleness": round(staleness_penalty, 2),
                "unmaintained_divergence": round(divergence_penalty, 2),
            }
        results.append(
            Score(
                dimension=dimension,
                value=_bounded(value),
                confidence=confidence,
                available_inputs=available,
                missing_inputs=missing,
                raw_inputs=raw_inputs,
            )
        )
    return results
