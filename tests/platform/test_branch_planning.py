from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fork_intelligence.domain.branch_planning import (
    BranchSignal,
    plan_branches,
)

NOW = datetime(2026, 7, 22, tzinfo=UTC)


def _signal(name: str, **overrides: object) -> BranchSignal:
    base: dict[str, object] = {
        "name": name,
        "head_sha": name.replace("/", "_") * 4,
        "is_default": False,
        "last_activity": NOW,
        "ahead": 1,
    }
    base.update(overrides)
    return BranchSignal(**base)  # type: ignore[arg-type]


def _by_name(plan: object) -> dict[str, object]:
    return {entry.name: entry for entry in plan.entries}  # type: ignore[attr-defined]


def test_default_branch_is_selected_first() -> None:
    plan = plan_branches(
        [
            _signal("feature", ahead=9, last_activity=NOW),
            _signal("main", is_default=True),
        ],
        cap=3,
    )

    assert plan.entries[0].name == "main"
    assert plan.entries[0].priority == 0
    assert plan.entries[0].is_default is True
    assert plan.entries[0].selection_reason == "default_branch"


def test_evaluable_candidates_are_ranked_ahead_then_activity_then_name() -> None:
    plan = plan_branches(
        [
            _signal("main", is_default=True),
            _signal("low", ahead=1, last_activity=NOW - timedelta(days=5)),
            _signal("high", ahead=10, last_activity=NOW - timedelta(days=30)),
            _signal("mid", ahead=5, last_activity=NOW),
        ],
        cap=4,
    )

    order = [entry.name for entry in plan.entries]
    assert order == ["main", "high", "mid", "low"]


def test_ties_break_on_branch_name_for_determinism() -> None:
    signals = [
        _signal("b", ahead=3, last_activity=NOW),
        _signal("a", ahead=3, last_activity=NOW),
        _signal("c", ahead=3, last_activity=NOW),
    ]
    forward = plan_branches([*signals], cap=5)
    reversed_input = plan_branches([*reversed(signals)], cap=5)

    assert [e.name for e in forward.entries] == ["a", "b", "c"]
    # Identical output regardless of input order (AC-RA-RBP-003.1).
    assert [e.name for e in forward.entries] == [e.name for e in reversed_input.entries]


def test_priorities_are_dense_and_unique_across_the_whole_plan() -> None:
    plan = plan_branches(
        [
            _signal("main", is_default=True),
            _signal("keep", ahead=5),
            _signal("drop", ahead=1),
            _signal("blind", ahead=None, last_activity=None, missing_input="probe_budget"),
        ],
        cap=2,
    )

    priorities = [entry.priority for entry in plan.entries]
    assert priorities == [0, 1, 2, 3]
    assert len(set(priorities)) == len(priorities)


def test_cap_excludes_lowest_ranked_and_names_the_cap() -> None:
    plan = plan_branches(
        [
            _signal("main", is_default=True),
            _signal("a", ahead=10),
            _signal("b", ahead=8),
            _signal("c", ahead=6),
        ],
        cap=2,
    )

    entries = _by_name(plan)
    # Default consumes one of two slots; only the top non-default fits.
    assert entries["main"].decision == "selected"
    assert entries["a"].decision == "selected"
    assert entries["b"].decision == "excluded"
    assert entries["b"].selection_reason == "branch_cap_exceeded"
    assert entries["c"].decision == "excluded"
    # Position relative to selected is carried by priority (AC-RA-RBP-002.2).
    assert entries["b"].priority < entries["c"].priority
    assert plan.selected == 2
    assert plan.excluded == 2


def test_fewer_candidates_than_cap_selects_all_eligible() -> None:
    plan = plan_branches(
        [
            _signal("main", is_default=True),
            _signal("only", ahead=3),
        ],
        cap=5,
    )

    assert plan.selected == 2
    assert plan.excluded == 0
    assert all(entry.decision == "selected" for entry in plan.entries)


def test_unevaluable_candidate_is_unevaluated_with_the_missing_input_named() -> None:
    plan = plan_branches(
        [
            _signal("main", is_default=True),
            _signal(
                "mystery",
                ahead=None,
                last_activity=None,
                missing_input="probe_budget_exhausted",
            ),
        ],
        cap=3,
    )

    entry = _by_name(plan)["mystery"]
    assert entry.decision == "unevaluated"
    assert entry.selection_reason == "probe_budget_exhausted"
    # Never a definitive exclusion reason (AC-RA-RBP-002.3).
    assert entry.selection_reason != "branch_cap_exceeded"
    assert plan.unevaluated == 1


def test_selection_reason_reflects_the_signals_present() -> None:
    plan = plan_branches(
        [
            _signal("main", is_default=True),
            _signal("both", ahead=4, last_activity=NOW),
            _signal("ahead_only", ahead=4, last_activity=None),
            _signal("active_only", ahead=0, last_activity=NOW),
        ],
        cap=5,
    )

    entries = _by_name(plan)
    assert entries["both"].selection_reason == "active_and_meaningfully_ahead"
    assert entries["ahead_only"].selection_reason == "meaningfully_ahead"
    assert entries["active_only"].selection_reason == "recently_active"


def test_coverage_counts_and_only_default_flag() -> None:
    default_only = plan_branches([_signal("main", is_default=True)], cap=3)
    assert default_only.only_default_selected is True
    assert default_only.considered == 1

    mixed = plan_branches(
        [
            _signal("main", is_default=True),
            _signal("extra", ahead=2),
        ],
        cap=3,
    )
    assert mixed.only_default_selected is False


def test_cap_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        plan_branches([_signal("main", is_default=True)], cap=0)


def test_plan_is_reproducible_across_repeated_calls() -> None:
    signals = [
        _signal("main", is_default=True),
        _signal("x", ahead=7, last_activity=NOW - timedelta(days=1)),
        _signal("y", ahead=7, last_activity=NOW - timedelta(days=1)),
        _signal("z", ahead=None, last_activity=None, missing_input="probe_budget"),
    ]

    first = plan_branches([*signals], cap=2)
    second = plan_branches([*signals], cap=2)

    assert first == second
