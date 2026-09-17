from __future__ import annotations

from fork_intelligence.domain.scoring import calculate_scores
from fork_intelligence.domain.star_growth import (
    STAR_GROWTH_VERSION,
    compare_to_upstream,
    summarize_star_growth,
)


def _weeks(*totals: int) -> list[dict[str, int]]:
    # Newest first, matching GitHub's history order.
    return [
        {"week": 1_700_000_000 - index * 604_800, "total": total}
        for index, total in enumerate(totals)
    ]


def test_windows_sum_created_stars_newest_first_without_replacing_count() -> None:
    history = _weeks(350, 12, 14, 9, 8, 10, 8, 12, 7, 11, 9, 10)
    summary = summarize_star_growth(1284, history)

    assert summary["count"] == 1284
    assert summary["count"] != sum(week["total"] for week in history)
    assert summary["created_last_4w"] == 350 + 12 + 14 + 9
    assert summary["created_last_12w"] == sum(week["total"] for week in history)
    assert summary["weekly_created"] == [10, 9, 11, 7, 12, 8, 10, 8, 9, 14, 12, 350]
    assert summary["weeks_observed"] == 12
    assert summary["current_week_partial"] is True
    assert summary["version"] == STAR_GROWTH_VERSION


def test_short_history_sums_only_observed_weeks() -> None:
    summary = summarize_star_growth(40, _weeks(3, 5))

    assert summary["count"] == 40
    assert summary["created_last_4w"] == 8
    assert summary["created_last_12w"] == 8
    assert summary["weekly_created"] == [5, 3]
    assert summary["weeks_observed"] == 2


def test_empty_history_keeps_count_and_zero_windows() -> None:
    summary = summarize_star_growth(7, [])

    assert summary == {
        "count": 7,
        "created_last_4w": 0,
        "created_last_12w": 0,
        "weekly_created": [],
        "weeks_observed": 0,
        "current_week_partial": True,
        "version": STAR_GROWTH_VERSION,
    }


def test_non_integer_totals_are_treated_as_zero() -> None:
    summary = summarize_star_growth(2, [{"week": 1, "total": True}, {"week": 2, "total": "3"}])

    assert summary["created_last_4w"] == 0
    assert summary["weekly_created"] == [0, 0]


def test_star_growth_metrics_do_not_change_scores() -> None:
    base = {"stars": 10, "forks": 2, "watchers": 1}
    with_growth = {
        **base,
        "star_growth": summarize_star_growth(9999, _weeks(500, 400, 300, 200)),
    }
    with_upstream = {
        **with_growth,
        "star_growth": {
            **with_growth["star_growth"],
            "vs_upstream": compare_to_upstream(
                with_growth["star_growth"],
                summarize_star_growth(1, _weeks(1, 1, 1, 1)),
                upstream_full_name="deskflow/deskflow",
            ),
        },
    }

    assert [score.value for score in calculate_scores(base)] == [
        score.value for score in calculate_scores(with_growth)
    ]
    assert [score.value for score in calculate_scores(base)] == [
        score.value for score in calculate_scores(with_upstream)
    ]


def test_vs_upstream_uses_lab_barrier_deskflow_windows() -> None:
    fork = summarize_star_growth(30879, _weeks(12, 30, 21, 24, 7, 35, 19, 34, 31, 44, 17, 22))
    parent = summarize_star_growth(
        28912, _weeks(127, 195, 198, 174, 172, 172, 166, 171, 171, 230, 154, 145)
    )

    comparison = compare_to_upstream(fork, parent, upstream_full_name="deskflow/deskflow")

    assert comparison == {
        "full_name": "deskflow/deskflow",
        "created_last_4w": 694,
        "created_last_12w": 2075,
        "ratio_4w": 0.13,
        "ratio_12w": 0.14,
    }
    assert fork["count"] == 30879
    assert "count" not in comparison
    assert "weekly_created" not in comparison
    assert comparison.keys().isdisjoint({"login", "avatar_url", "user", "stargazers"})


def test_vs_upstream_is_omitted_when_fork_twelve_week_series_is_zero() -> None:
    fork = summarize_star_growth(47, _weeks(*([0] * 12)))
    parent = summarize_star_growth(74746, _weeks(486, 2121, 53, 41))

    assert compare_to_upstream(fork, parent, upstream_full_name="pallets/flask") is None


def test_vs_upstream_omits_ratio_when_parent_window_is_zero() -> None:
    fork = summarize_star_growth(100, _weeks(10, 10, 10, 10))
    parent = summarize_star_growth(1, _weeks(0, 0, 0, 0))

    comparison = compare_to_upstream(fork, parent, upstream_full_name="lab/quiet")

    assert comparison is not None
    assert comparison["created_last_4w"] == 0
    assert "ratio_4w" not in comparison
    assert "ratio_12w" not in comparison
