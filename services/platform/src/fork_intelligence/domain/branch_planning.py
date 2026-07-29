"""Deterministic multi-branch planning.

A pure function over normalized branch-candidate signals. Given the same
candidates, cap, and planner version it produces the same ordering, decisions,
and reasons every time -- the property REQ-RA-RBP-003 depends on -- so it is
kept free of I/O and clocks. The pipeline gathers the signals and persists the
result; this module only decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

BranchDecision = Literal["selected", "excluded", "unevaluated"]

# Bump when the selection rules below change. WO-1 recorded only the default
# branch under "2026.07.1"; multi-branch selection is a new rule set, and a new
# version so historical plans are never rewritten (AC-RA-RBP-003.2).
BRANCH_PLANNER_VERSION = "2026.07.2"


@dataclass(frozen=True, slots=True)
class BranchSignal:
    """What was observed about one candidate branch.

    ``last_activity`` and ``ahead`` are ``None`` when the signal could not be
    established within the probe budget. A candidate missing either signal is
    unevaluable and must not be assigned a definitive exclusion
    (AC-RA-RBP-002.3).
    """

    name: str
    head_sha: str
    is_default: bool
    last_activity: datetime | None = None
    ahead: int | None = None
    #: Names why a signal is missing, e.g. "probe_budget_exhausted". Required
    #: when the candidate is unevaluable so the gap is explained, not guessed.
    missing_input: str | None = None


@dataclass(frozen=True, slots=True)
class PlannedBranch:
    name: str
    head_sha: str
    is_default: bool
    priority: int
    decision: BranchDecision
    selection_reason: str | None


@dataclass(frozen=True, slots=True)
class BranchPlan:
    entries: tuple[PlannedBranch, ...]

    @property
    def considered(self) -> int:
        return len(self.entries)

    @property
    def selected(self) -> int:
        return sum(1 for entry in self.entries if entry.decision == "selected")

    @property
    def excluded(self) -> int:
        return sum(1 for entry in self.entries if entry.decision == "excluded")

    @property
    def unevaluated(self) -> int:
        return sum(1 for entry in self.entries if entry.decision == "unevaluated")

    @property
    def selected_entries(self) -> tuple[PlannedBranch, ...]:
        return tuple(entry for entry in self.entries if entry.decision == "selected")

    @property
    def only_default_selected(self) -> bool:
        """True when the default branch is the sole selected candidate."""
        selected = self.selected_entries
        return len(selected) == 1 and selected[0].is_default


def _rank_key(signal: BranchSignal) -> tuple[int, float, str]:
    """Total order over evaluable non-default candidates, ahead first.

    Every component is total and the final tie-break is the branch name, so no
    two distinct candidates can compare equal. That is what makes the ordering
    reproducible rather than dependent on input order.
    """
    ahead = signal.ahead or 0
    # datetime is not directly usable as a stable numeric tie-breaker across
    # None, so absent activity sorts last via a sentinel timestamp.
    activity = signal.last_activity.timestamp() if signal.last_activity is not None else 0.0
    # Negated so that Python's ascending sort places larger values first.
    return (-ahead, -activity, signal.name)


def _is_evaluable(signal: BranchSignal) -> bool:
    # A candidate is evaluable when at least one positive signal is present.
    # Both signals absent means the planner has nothing to rank it on.
    return signal.last_activity is not None or signal.ahead is not None


def _selection_reason(signal: BranchSignal) -> str:
    ahead = (signal.ahead or 0) > 0
    active = signal.last_activity is not None
    if ahead and active:
        return "active_and_meaningfully_ahead"
    if ahead:
        return "meaningfully_ahead"
    return "recently_active"


def plan_branches(signals: list[BranchSignal], *, cap: int) -> BranchPlan:
    """Produce a deterministic branch plan.

    The default branch is selected first (AC-RA-RBP-001.2). Remaining evaluable
    candidates are ranked and selected up to the effective cap
    (AC-RA-RBP-001.3); those beyond it are excluded by the cap
    (AC-RA-RBP-002.2). Candidates whose signals could not be established are
    left unevaluated with the missing input named, never given a definitive
    exclusion reason (AC-RA-RBP-002.3). ``priority`` is a dense, unique rank
    over the whole plan, satisfying the per-repository uniqueness constraint
    the persistence layer enforces.
    """
    if cap < 1:
        raise ValueError("effective branch cap must be at least 1")

    default = next((signal for signal in signals if signal.is_default), None)
    others = [signal for signal in signals if not signal.is_default]

    evaluable = sorted((s for s in others if _is_evaluable(s)), key=_rank_key)
    unevaluable = sorted((s for s in others if not _is_evaluable(s)), key=lambda s: s.name)

    entries: list[PlannedBranch] = []
    priority = 0

    if default is not None:
        entries.append(
            PlannedBranch(
                name=default.name,
                head_sha=default.head_sha,
                is_default=True,
                priority=priority,
                decision="selected",
                selection_reason="default_branch",
            )
        )
        priority += 1

    # The default already consumes one slot when present (AC-RA-RBP-001.2/.3:
    # the default is selected first, then others fill the remaining cap).
    remaining_slots = cap - (1 if default is not None else 0)

    for index, signal in enumerate(evaluable):
        selected = index < remaining_slots
        entries.append(
            PlannedBranch(
                name=signal.name,
                head_sha=signal.head_sha,
                is_default=False,
                priority=priority,
                decision="selected" if selected else "excluded",
                selection_reason=(_selection_reason(signal) if selected else "branch_cap_exceeded"),
            )
        )
        priority += 1

    for signal in unevaluable:
        entries.append(
            PlannedBranch(
                name=signal.name,
                head_sha=signal.head_sha,
                is_default=False,
                priority=priority,
                decision="unevaluated",
                selection_reason=signal.missing_input or "signal_unavailable",
            )
        )
        priority += 1

    return BranchPlan(entries=tuple(entries))
