"""Clock system — tension accumulators that drive event pacing (technical §5.3).

A *clock* is a floating-point accumulator tied to a target event. Each tick
adds a value (from narrative triggers, passage of time, etc.). When the
clock reaches its threshold, the associated event is force-inserted into
the schedule.

Clocks contribute to event selection weights via ``compute_weight`` in
``events.py``. The integration there duck-types on ``target_event_id``
and ``current`` — this module provides the concrete dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass
class ClockTick:
    """A single increment to a clock.

    Stored for auditability; the clock's ``current`` value is the running
    sum but keeping ticks allows narrative hooks to inspect *why* a clock
    is ticking.
    """

    amount: float
    reason: str = ""

    def to_dict(self) -> dict:
        return {"amount": self.amount, "reason": self.reason}

    @classmethod
    def from_dict(cls, d: Mapping) -> "ClockTick":
        return cls(amount=float(d["amount"]), reason=str(d.get("reason", "")))


@dataclass
class Clock:
    """A tension accumulator targeting a specific event.

    Fields:
        id: unique identifier for this clock.
        target_event_id: the event that fires when threshold is reached.
        threshold: value at which the clock triggers a force-insert.
        current: running accumulator.
        ticks: history of individual increments.
        triggered: whether the clock has already fired.
        recurring: if True, the clock resets after triggering instead of
                   being spent.
    """

    id: str
    target_event_id: str
    threshold: float = 1.0
    current: float = 0.0
    ticks: list[ClockTick] = field(default_factory=list)
    triggered: bool = False
    recurring: bool = False

    def tick(self, amount: float, reason: str = "") -> bool:
        """Advance the clock. Returns True if this tick caused a trigger.

        Once triggered (and not recurring), further ticks are ignored.
        """
        if self.triggered and not self.recurring:
            return False
        self.ticks.append(ClockTick(amount=amount, reason=reason))
        self.current += amount
        if self.current >= self.threshold and not self.triggered:
            self.triggered = True
            return True
        return False

    def reset(self) -> None:
        """Reset the clock for recurring use."""
        self.current = 0.0
        self.triggered = False
        self.ticks.clear()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "target_event_id": self.target_event_id,
            "threshold": self.threshold,
            "current": self.current,
            "ticks": [t.to_dict() for t in self.ticks],
            "triggered": self.triggered,
            "recurring": self.recurring,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "Clock":
        return cls(
            id=d["id"],
            target_event_id=d["target_event_id"],
            threshold=float(d.get("threshold", 1.0)),
            current=float(d.get("current", 0.0)),
            ticks=[ClockTick.from_dict(t) for t in d.get("ticks", [])],
            triggered=bool(d.get("triggered", False)),
            recurring=bool(d.get("recurring", False)),
        )


# --- Batch operations --------------------------------------------------------


def tick_clocks(
    clocks: Sequence[Clock],
    amount: float,
    reason: str = "",
    *,
    filter_ids: set[str] | None = None,
) -> list[Clock]:
    """Tick a set of clocks and return those that triggered.

    If *filter_ids* is provided, only clocks whose ``id`` is in the set
    are ticked. Others are left untouched.
    """
    triggered: list[Clock] = []
    for clock in clocks:
        if filter_ids is not None and clock.id not in filter_ids:
            continue
        if clock.tick(amount, reason):
            triggered.append(clock)
    return triggered


def check_triggers(
    clocks: Sequence[Clock],
) -> list[Clock]:
    """Return all clocks that have reached their threshold but have not been
    acted upon yet (still ``triggered=True``).

    This is a read-only query — use ``force_insert_triggered`` to act on them.
    """
    return [c for c in clocks if c.triggered]


def force_insert_triggered(
    clocks: Sequence[Clock],
    schedule: "WeekSchedule",  # noqa: F821 — forward ref to avoid circular
) -> list[str]:
    """For each triggered clock, force-insert its target event into the
    schedule. Returns the list of event IDs that were force-inserted.

    Recurring clocks are reset after force-insert; non-recurring clocks
    remain triggered (spent) and are skipped on future calls.
    """
    from .schedule import WeekSchedule  # deferred to avoid circular import

    inserted: list[str] = []
    for clock in clocks:
        if not clock.triggered:
            continue
        # Only force-insert once per trigger.
        already = any(
            s.forced_event_id == clock.target_event_id
            for s in schedule.slots
        )
        if already:
            continue
        if schedule.force_next(clock.target_event_id):
            inserted.append(clock.target_event_id)
            if clock.recurring:
                clock.reset()
    return inserted
