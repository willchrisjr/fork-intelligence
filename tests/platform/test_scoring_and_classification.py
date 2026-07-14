from __future__ import annotations

import pytest

from fork_intelligence.domain.classification import classify_repository
from fork_intelligence.domain.scoring import calculate_scores


def _complete_metrics() -> dict[str, object]:
    return {
        "stars": 100,
        "forks": 25,
        "watchers": 10,
        "days_since_push": 12,
        "commits_90d": 18,
        "commits_365d": 80,
        "active_months_12m": 10,
        "releases_365d": 4,
        "contributors": 8,
        "has_tests": True,
        "has_ci": True,
        "unique_patches": 35,
        "source_files_changed": 60,
        "test_files_changed": 20,
        "ahead": 45,
        "behind": 3,
        "files_changed": 100,
        "directories_changed": 12,
        "dependency_changes": 2,
        "days_since_common_commit": 30,
        "conflict_estimate": 0.1,
        "patch_overlap_upstream": 0.15,
    }


def test_scoring_produces_separate_bounded_dimensions_with_full_confidence() -> None:
    scores = {score.dimension: score for score in calculate_scores(_complete_metrics())}

    assert set(scores) == {
        "popularity",
        "recent_activity",
        "sustained_activity",
        "maintenance",
        "original_development",
        "divergence",
        "adoption",
        "upstream_compatibility",
        "maintained_successor",
        "unmerged_innovation",
    }
    assert all(0 <= score.value <= 100 for score in scores.values())
    assert all(score.confidence == 1 for score in scores.values())
    assert all(score.version.startswith("score-") for score in scores.values())


def test_maintained_successor_profile_records_exact_formula_and_penalties() -> None:
    score = next(
        item
        for item in calculate_scores(_complete_metrics())
        if item.dimension == "maintained_successor"
    )

    assert score.raw_inputs["profile_formula"] == {
        "maintenance": 0.30,
        "sustained_activity": 0.15,
        "adoption": 0.15,
        "original_development": 0.15,
        "releases": 0.10,
        "contributor_breadth": 0.10,
        "upstream_sync": 0.05,
    }
    assert sum(score.raw_inputs["profile_formula"].values()) == pytest.approx(1.0)
    assert score.raw_inputs["penalties"] == {"staleness": 0.0, "unmaintained_divergence": 0.0}


def test_stale_unmaintained_divergence_is_penalized() -> None:
    healthy = _complete_metrics()
    stale = {**healthy, "days_since_push": 1095, "active_months_12m": 0}

    healthy_score = next(
        item for item in calculate_scores(healthy) if item.dimension == "maintained_successor"
    )
    stale_score = next(
        item for item in calculate_scores(stale) if item.dimension == "maintained_successor"
    )

    assert stale_score.value < healthy_score.value
    assert stale_score.raw_inputs["penalties"]["staleness"] > 0
    assert stale_score.raw_inputs["penalties"]["unmaintained_divergence"] > 0


def test_score_confidence_tracks_only_available_inputs() -> None:
    scores = {score.dimension: score for score in calculate_scores({"stars": 5})}

    popularity = scores["popularity"]
    assert popularity.available_inputs == ["stars"]
    assert popularity.missing_inputs == ["forks", "watchers"]
    assert popularity.confidence == pytest.approx(1 / 3, abs=0.001)


def test_low_coverage_classification_returns_unknown() -> None:
    classification = classify_repository({"ahead": 3, "behind": 1})

    assert classification.label == "unknown"
    assert classification.confidence < 0.5
    assert set(classification.missing_inputs) == {
        "unique_patches",
        "days_since_push",
        "active_months_12m",
    }
    assert "coverage" in classification.reasons[0].lower()


@pytest.mark.parametrize(
    ("metrics", "label"),
    [
        (
            {
                "ahead": 0,
                "behind": 0,
                "unique_patches": 0,
                "days_since_push": 20,
                "active_months_12m": 0,
            },
            "mirror",
        ),
        (
            {
                "ahead": 25,
                "behind": 5,
                "unique_patches": 15,
                "days_since_push": 10,
                "active_months_12m": 8,
            },
            "maintained_continuation",
        ),
        (
            {
                "ahead": 40,
                "behind": 200,
                "unique_patches": 30,
                "days_since_push": 500,
                "active_months_12m": 2,
                "source_files_changed": 100,
                "dependency_changes": 8,
            },
            "independent_direction",
        ),
    ],
)
def test_evidence_patterns_are_classified_deterministically(
    metrics: dict[str, object], label: str
) -> None:
    first = classify_repository(metrics)
    second = classify_repository(metrics)

    assert first == second
    assert first.label == label
    assert first.confidence > 0.4
