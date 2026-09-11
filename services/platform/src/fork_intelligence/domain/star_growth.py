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


def _nonneg_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0
