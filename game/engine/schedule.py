"""Week schedule — event slot planning (technical §5.3).

A WeekSchedule is a skeleton of slots for a given week. The schedule
generator builds a standard week (e.g. drama → training → pregame →
game phases → postgame) and the engine fills event slots during play.

Phase 11.5B layered a calendar onto the existing flat slot list: each
``EventSlot`` knows its ``weekday`` and ``slot`` (when in the day),
and weather draws once per weekday rather than per slot. This keeps
the existing iteration order while exposing day-level structure for
the world clock and status bar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

from .clock import Slot, Weekday


class BlockType(str, Enum):
    """Broad category for a schedule slot."""

    DRAMA = "drama"
    TRAINING = "training"
    PREGAME = "pregame"
    GAME_PHASE = "game_phase"
    POSTGAME = "postgame"
    DOWNTIME = "downtime"


@dataclass
class EventSlot:
    """One scheduled moment in a week.

    May be pre-filled (forced by a clock or arc) or left open for the
    selection pipeline to populate during play. ``weekday`` and ``slot``
    place this moment on the calendar — ``None`` is accepted for
    backward compatibility but ``generate_week`` always populates them.
    """

    block_type: BlockType
    phase_index: int = -1  # game-phase number, or -1 for non-game slots
    forced_event_id: str | None = None  # set by clock threshold / arc
    resolved_event_id: str | None = None  # filled after selection
    resolved_branch: str | None = None  # filled after play
    weekday: Weekday | None = None  # which day the slot lives on
    slot: Slot | None = None  # which slot of the day

    def to_dict(self) -> dict:
        return {
            "block_type": self.block_type.value,
            "phase_index": self.phase_index,
            "forced_event_id": self.forced_event_id,
            "resolved_event_id": self.resolved_event_id,
            "resolved_branch": self.resolved_branch,
            "weekday": self.weekday.value if self.weekday is not None else None,
            "slot": self.slot.value if self.slot is not None else None,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "EventSlot":
        wd = d.get("weekday")
        sl = d.get("slot")
        return cls(
            block_type=BlockType(d["block_type"]),
            phase_index=int(d.get("phase_index", -1)),
            forced_event_id=d.get("forced_event_id"),
            resolved_event_id=d.get("resolved_event_id"),
            resolved_branch=d.get("resolved_branch"),
            weekday=Weekday(wd) if wd is not None else None,
            slot=Slot(sl) if sl is not None else None,
        )


@dataclass
class WeekSchedule:
    """Ordered list of event slots for a single week.

    Weather is drawn once per weekday at ``start_week`` time:
    ``weather_tendency`` is the week's "mode" and ``daily_weathers``
    maps each weekday's enum value to the day's actual weather draw.
    All slots on a given day share that day's weather (so all eight
    match phases use the matchday draw).
    """

    season: int
    week: int
    slots: list[EventSlot] = field(default_factory=list)
    weather_tendency: str | None = None
    daily_weathers: dict[str, str] = field(default_factory=dict)

    def pending_slots(self) -> list[EventSlot]:
        """Slots that have not yet been resolved."""
        return [s for s in self.slots if s.resolved_event_id is None]

    def force_next(self, event_id: str, block_type: BlockType | None = None) -> bool:
        """Force an event into the first available pending slot.

        If *block_type* is given, only slots of that type are considered.
        Returns True if a slot was found and filled, False otherwise.
        """
        for slot in self.pending_slots():
            if block_type is not None and slot.block_type != block_type:
                continue
            slot.forced_event_id = event_id
            return True
        return False

    def weather_for(self, weekday: Weekday) -> str | None:
        """Lookup helper — returns the weather enum value for a day."""
        return self.daily_weathers.get(weekday.value)

    def to_dict(self) -> dict:
        return {
            "season": self.season,
            "week": self.week,
            "slots": [s.to_dict() for s in self.slots],
            "weather_tendency": self.weather_tendency,
            "daily_weathers": dict(self.daily_weathers),
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "WeekSchedule":
        return cls(
            season=int(d["season"]),
            week=int(d["week"]),
            slots=[EventSlot.from_dict(s) for s in d.get("slots", [])],
            weather_tendency=d.get("weather_tendency"),
            daily_weathers=dict(d.get("daily_weathers", {})),
        )


# --- Skeleton generators -----------------------------------------------------

# Default week template: 2 drama, 1 training, 1 pregame, N game phases,
# 1 postgame, 1 downtime.
DEFAULT_GAME_PHASES = 8


# Default calendar: which weekday and slot each block falls on. The
# ordering below preserves the original drama → training → pregame →
# match → postgame → downtime sequence while spreading it across the
# week so the world clock advances naturally between blocks.
_CALENDAR: list[tuple[BlockType, Weekday, Slot]] = [
    (BlockType.DRAMA,    Weekday.MON, Slot.MORNING),
    (BlockType.DRAMA,    Weekday.MON, Slot.AFTERNOON),
    (BlockType.TRAINING, Weekday.TUE, Slot.MIDDAY),
    (BlockType.PREGAME,  Weekday.FRI, Slot.AFTERNOON),
    # Match phases collapse to Sat afternoon (one slot, eight phases
    # within). Postgame on Sat evening, downtime on Sun afternoon.
]


def generate_week(
    season: int,
    week: int,
    *,
    game_phases: int = DEFAULT_GAME_PHASES,
    drama_slots: int = 2,
    training_slots: int = 1,
    include_downtime: bool = True,
) -> WeekSchedule:
    """Build a standard week skeleton.

    Ordering: drama → training → pregame → game phases → postgame →
    downtime. Each slot is tagged with its weekday + within-day slot so
    the world clock can fast-forward correctly between them.

    The non-default ``drama_slots`` / ``training_slots`` parameters
    extend the calendar with morning fillers on free weekdays so the
    skeleton still has a stable shape under tweaks.
    """
    free_morning_days = (Weekday.MON, Weekday.WED, Weekday.THU)

    slots: list[EventSlot] = []
    drama_added = 0
    while drama_added < drama_slots:
        # Pull from _CALENDAR's drama slots first; fall back to free mornings.
        if drama_added < 2:
            _, wd, sl = _CALENDAR[drama_added]
        else:
            wd = free_morning_days[(drama_added - 2) % len(free_morning_days)]
            sl = Slot.MORNING
        slots.append(EventSlot(block_type=BlockType.DRAMA, weekday=wd, slot=sl))
        drama_added += 1

    for i in range(training_slots):
        if i == 0:
            wd, sl = Weekday.TUE, Slot.MIDDAY
        else:
            wd = (Weekday.WED, Weekday.THU)[i % 2]
            sl = Slot.MIDDAY
        slots.append(EventSlot(block_type=BlockType.TRAINING, weekday=wd, slot=sl))

    slots.append(EventSlot(
        block_type=BlockType.PREGAME, weekday=Weekday.FRI, slot=Slot.AFTERNOON,
    ))
    for i in range(game_phases):
        slots.append(EventSlot(
            block_type=BlockType.GAME_PHASE, phase_index=i,
            weekday=Weekday.SAT, slot=Slot.AFTERNOON,
        ))
    slots.append(EventSlot(
        block_type=BlockType.POSTGAME, weekday=Weekday.SAT, slot=Slot.EVENING,
    ))
    if include_downtime:
        slots.append(EventSlot(
            block_type=BlockType.DOWNTIME, weekday=Weekday.SUN, slot=Slot.AFTERNOON,
        ))
    return WeekSchedule(season=season, week=week, slots=slots)
