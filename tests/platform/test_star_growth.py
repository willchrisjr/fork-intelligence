from __future__ import annotations

from fork_intelligence.domain.star_growth import (
    STAR_GROWTH_VERSION,
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
