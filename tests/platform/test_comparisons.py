from fork_intelligence.domain.comparisons import (
    ComparisonRepository,
    build_comparison_result,
)


def test_comparison_result_exposes_web_read_models_and_raw_pairs() -> None:
    upstream = ComparisonRepository(
        repository_id="upstream",
        full_name="source/project",
        role="upstream",
        default_branch="main",
        head_sha="a" * 40,
        metrics={"file_composition": {"application_source": 4}},
    )
    left = ComparisonRepository(
        repository_id="left",
        full_name="left/project",
        role="fork",
        default_branch="main",
        head_sha="b" * 40,
        metrics={
            "changed_paths": ["src/a.py", "tests/test_a.py"],
            "patch_fingerprints": ["patch-1"],
            "aggregate_patch_id": "aggregate-1",
            "file_composition": {"application_source": 1, "tests": 1},
        },
    )
    right = ComparisonRepository(
        repository_id="right",
        full_name="right/project",
        role="fork",
        default_branch="next",
        head_sha=None,
        metrics={
            "changed_paths": ["src/a.py", "docs/guide.md"],
            "patch_fingerprints": ["patch-1", "patch-2"],
            "aggregate_patch_id": "aggregate-1",
            "file_composition": {"application_source": 1, "documentation": 1},
        },
    )

    result = build_comparison_result([upstream, left, right])

    assert [item["role"] for item in result["repositories"]] == [
        "upstream",
        "fork",
        "fork",
    ]
    assert result["repositories"][2]["default_branch"] == "next"
    assert len(result["pairs"]) == 3
    fork_overlap = next(
        item
        for item in result["overlap"]
        if item["left_repository_id"] == "left" and item["right_repository_id"] == "right"
    )
    assert fork_overlap["shared_changed_paths"] == ["src/a.py"]
    assert fork_overlap["shared_patch_ids"] == ["patch-1"]
    assert fork_overlap["aggregate_match"] is True
    assert result["composition"][1]["categories"]["tests"] == 1
    assert result["integration"][2]["disclosure"] == "approximation_not_merge_simulation"
