"""Privacy-safe star-growth summaries from GitHub aggregate endpoints.

The count endpoint is the current total. History buckets are stars *created*
that week, newest first — never a running total and never a substitute for
count. Velocity is an indicator, not proof of quality.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

STAR_GROWTH_VERSION = "star-growth-2026.09.1"
STAR_GROWTH_HISTORY_WEEKS = 12
STAR_GROWTH_RECENT_WEEKS = 4

# Always disclosed: GitHub does not guarantee UTC-aligned week/day boundaries,
# and the newest bucket is the in-progress week.
CURRENT_WEEK_PARTIAL = True


def summarize_star_growth(
    count: int, weeks_newest_first: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Build the evidence-panel payload from count + weekly created-star totals.

    ``count`` must come from ``GET .../stargazers/count``. History ``total``
    values are summed only for the 4- and 12-week created-star windows.
    """
    totals = [_nonneg_int(week.get("total")) for week in weeks_newest_first][
        :STAR_GROWTH_HISTORY_WEEKS
    ]
    return {
        "count": _nonneg_int(count),
        "created_last_4w": sum(totals[:STAR_GROWTH_RECENT_WEEKS]),
        "created_last_12w": sum(totals[:STAR_GROWTH_HISTORY_WEEKS]),
        "weekly_created": list(reversed(totals)),
        "weeks_observed": len(totals),
        "current_week_partial": CURRENT_WEEK_PARTIAL,
        "version": STAR_GROWTH_VERSION,
    }


def compare_to_upstream(
    fork: Mapping[str, Any],
    upstream: Mapping[str, Any],
    *,
    upstream_full_name: str,
) -> dict[str, Any] | None:
    """Compare fork created-star windows to a known parent/source.

    Returns identity-free 4w/12w aggregates and ratios, or ``None`` when the
    fork's 12-week series is empty (the comparison restates a dead fork).
    Never copies count, weekly series, or identity-bearing keys.
    """
    fork_4 = _nonneg_int(fork.get("created_last_4w"))
    fork_12 = _nonneg_int(fork.get("created_last_12w"))
    upstream_4 = _nonneg_int(upstream.get("created_last_4w"))
    upstream_12 = _nonneg_int(upstream.get("created_last_12w"))
    if fork_12 == 0:
        return None
    comparison: dict[str, Any] = {
        "full_name": upstream_full_name,
        "created_last_4w": upstream_4,
        "created_last_12w": upstream_12,
    }
    ratio_4 = _created_ratio(fork_4, upstream_4)
    ratio_12 = _created_ratio(fork_12, upstream_12)
    if ratio_4 is not None:
        comparison["ratio_4w"] = ratio_4
    if ratio_12 is not None:
        comparison["ratio_12w"] = ratio_12
    return comparison


def _created_ratio(fork_total: int, upstream_total: int) -> float | None:
    if upstream_total <= 0:
        return None
    return round(fork_total / upstream_total, 2)


def _nonneg_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0
