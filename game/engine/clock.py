"""World clock and slot grid (Phase 11.5A).

Two parallel time concepts the rest of the engine reads:

- **Slots** — four per day, anchored at fixed hours: morning 08:00,
  midday 12:00, afternoon 16:00, evening 20:00. Each is a 4-hour
  spawn window. Night (00:00–07:59) is auto-skipped.
- **`WorldClock(week, weekday, hour, minute)`** — hour-precision time
  that advances continuously as events resolve and the player moves.

The clock is the source of truth. ``time_of_day_for_hour`` projects it
onto the colour-grade enum so atmosphere derives from real time, not
the block being played.

This module is intentionally pure data + pure functions. Mutation of
``WorldClock`` instances goes through :meth:`WorldClock.advance`, which
also rolls forward into the next day when the evening slot ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Weekday(str, Enum):
    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"


_WEEKDAY_ORDER: tuple[Weekday, ...] = (
    Weekday.MON, Weekday.TUE, Weekday.WED, Weekday.THU,
    Weekday.FRI, Weekday.SAT, Weekday.SUN,
)


def next_weekday(day: Weekday) -> tuple[Weekday, bool]:
    """Return ``(next_weekday, week_rollover)`` — when SUN advances to
    MON the second value is True so the caller knows to bump the
    week counter."""
    idx = _WEEKDAY_ORDER.index(day)
    if idx == len(_WEEKDAY_ORDER) - 1:
        return _WEEKDAY_ORDER[0], True
    return _WEEKDAY_ORDER[idx + 1], False


class Slot(str, Enum):
    MORNING = "morning"
    MIDDAY = "midday"
    AFTERNOON = "afternoon"
    EVENING = "evening"


SLOT_START_HOUR: dict[Slot, int] = {
    Slot.MORNING: 8,
    Slot.MIDDAY: 12,
    Slot.AFTERNOON: 16,
    Slot.EVENING: 20,
}

# End hour of each slot (exclusive). EVENING runs to 24 (midnight).
SLOT_END_HOUR: dict[Slot, int] = {
    Slot.MORNING: 12,
    Slot.MIDDAY: 16,
    Slot.AFTERNOON: 20,
    Slot.EVENING: 24,
}

_SLOT_ORDER: tuple[Slot, ...] = (
    Slot.MORNING, Slot.MIDDAY, Slot.AFTERNOON, Slot.EVENING,
)


def slot_for_hour(hour: int) -> Slot | None:
    """Map an hour-of-day (0–23) to the slot it falls in.

    Returns ``None`` for the night window (00–08). Callers in
    ``atmosphere()`` clamp to the next morning.
    """
    if hour < 8:
        return None
    for slot in _SLOT_ORDER:
        if SLOT_START_HOUR[slot] <= hour < SLOT_END_HOUR[slot]:
            return slot
    return None


def next_slot(slot: Slot) -> tuple[Slot, bool]:
    """Return ``(next_slot, day_rollover)``. After EVENING comes MORNING
    of the next day."""
    idx = _SLOT_ORDER.index(slot)
    if idx == len(_SLOT_ORDER) - 1:
        return _SLOT_ORDER[0], True
    return _SLOT_ORDER[idx + 1], False


# ---------------------------------------------------------------------------
# WorldClock
# ---------------------------------------------------------------------------


@dataclass
class WorldClock:
    """Hour-precision world time. Mutated through :meth:`advance` so the
    night-skip and weekday rollover invariants stay enforced.

    ``week`` is 1-based (matches existing ``WeekPhase.week``).
    """

    week: int = 1
    weekday: Weekday = Weekday.MON
    hour: int = 8
    minute: int = 0

    # ---- Slot lookup --------------------------------------------------

    def current_slot(self) -> Slot:
        """The slot the clock is currently in. The night window
        auto-resolves to the upcoming morning."""
        slot = slot_for_hour(self.hour)
        return slot if slot is not None else Slot.MORNING

    def in_night(self) -> bool:
        """True between the end of EVENING and the start of MORNING."""
        return slot_for_hour(self.hour) is None

    def hour_minute(self) -> str:
        """Status-bar friendly ``HH:MM`` string."""
        return f"{self.hour:02d}:{self.minute:02d}"

    def total_minutes_in_day(self) -> int:
        return self.hour * 60 + self.minute

    def day_ordinal(self) -> int:
        """Absolute day index since the start of the game (week 1 Monday
        == 0). Lets callers tell whether two timestamps fall on the same
        calendar day or are separated by a gap — used to decide when an
        arc thread has lapsed long enough to warrant a recap."""
        return (self.week - 1) * 7 + _WEEKDAY_ORDER.index(self.weekday)

    # ---- Advance / fast-forward --------------------------------------

    def advance(self, minutes: int) -> None:
        """Move the clock forward by ``minutes``.

        Crosses day and week boundaries automatically. The night window
        is skipped: any advance landing between 00:00 and 08:00 jumps
        forward to 08:00 of that day.
        """
        if minutes < 0:
            raise ValueError("clock can only advance forward")
        if minutes == 0:
            return
        total = self.total_minutes_in_day() + minutes
        days_added = total // (24 * 60)
        remaining = total % (24 * 60)
        for _ in range(days_added):
            self._roll_day()
        self.hour = remaining // 60
        self.minute = remaining % 60
        self._skip_night()

    def fast_forward_to_slot(self, slot: Slot) -> int:
        """Jump to the start of ``slot``. If that slot is earlier in the
        day, advance to the same slot tomorrow. Returns the number of
        minutes advanced.

        Used by the slot fast-forward cue: when the current event ends
        and there isn't enough time before the next slot to fit another,
        the engine calls this to land at the next anchor.
        """
        target_hour = SLOT_START_HOUR[slot]
        before = self.total_minutes_in_day()
        target_minutes = target_hour * 60
        if target_minutes <= before:
            # Wrap to tomorrow's same slot.
            delta = (24 * 60 - before) + target_minutes
        else:
            delta = target_minutes - before
        self.advance(delta)
        return delta

    def minutes_until_next_slot(self) -> int:
        """How long until the *next* slot anchor — used by the status
        bar's transition warning. The current slot is excluded; this is
        always strictly forward.
        """
        current = self.current_slot()
        nxt, _rollover = next_slot(current)
        target_hour = SLOT_START_HOUR[nxt]
        before = self.total_minutes_in_day()
        target_minutes = target_hour * 60
        if target_minutes <= before:
            return (24 * 60 - before) + target_minutes
        return target_minutes - before

    # ---- Internal -----------------------------------------------------

    def _roll_day(self) -> None:
        nxt, week_rollover = next_weekday(self.weekday)
        self.weekday = nxt
        if week_rollover:
            self.week += 1

    def _skip_night(self) -> None:
        """If the clock landed in the night window, jump to 08:00 of
        the same day so the player never sees an unactionable hour."""
        if self.in_night():
            self.hour = 8
            self.minute = 0

    # ---- Persistence --------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "week": self.week,
            "weekday": self.weekday.value,
            "hour": self.hour,
            "minute": self.minute,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "WorldClock":
        return cls(
            week=int(d.get("week", 1)),
            weekday=Weekday(d.get("weekday", Weekday.MON.value)),
            hour=int(d.get("hour", 8)),
            minute=int(d.get("minute", 0)),
        )

    def copy(self) -> "WorldClock":
        return WorldClock(
            week=self.week,
            weekday=self.weekday,
            hour=self.hour,
            minute=self.minute,
        )
