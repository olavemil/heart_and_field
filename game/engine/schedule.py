"""Week schedule — event slot planning (technical §5.3).

A WeekSchedule is a skeleton of slots for a given week. The schedule
generator builds a standard week (e.g. drama → training → pregame →
game phases → postgame) and the engine fills event slots during play.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


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
    selection pipeline to populate during play.
    """

    block_type: BlockType
    phase_index: int = -1  # game-phase number, or -1 for non-game slots
    forced_event_id: str | None = None  # set by clock threshold / arc
    resolved_event_id: str | None = None  # filled after selection
    resolved_branch: str | None = None  # filled after play

    def to_dict(self) -> dict:
        return {
            "block_type": self.block_type.value,
            "phase_index": self.phase_index,
            "forced_event_id": self.forced_event_id,
            "resolved_event_id": self.resolved_event_id,
            "resolved_branch": self.resolved_branch,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "EventSlot":
        return cls(
            block_type=BlockType(d["block_type"]),
            phase_index=int(d.get("phase_index", -1)),
            forced_event_id=d.get("forced_event_id"),
            resolved_event_id=d.get("resolved_event_id"),
            resolved_branch=d.get("resolved_branch"),
        )


@dataclass
class WeekSchedule:
    """Ordered list of event slots for a single week."""

    season: int
    week: int
    slots: list[EventSlot] = field(default_factory=list)

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

    def to_dict(self) -> dict:
        return {
            "season": self.season,
            "week": self.week,
            "slots": [s.to_dict() for s in self.slots],
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "WeekSchedule":
        return cls(
            season=int(d["season"]),
            week=int(d["week"]),
            slots=[EventSlot.from_dict(s) for s in d.get("slots", [])],
        )


# --- Skeleton generators -----------------------------------------------------

# Default week template: 2 drama, 1 training, 1 pregame, N game phases,
# 1 postgame, 1 downtime.
DEFAULT_GAME_PHASES = 8


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

    Ordering: drama → training → pregame → game phases → postgame → downtime.
    """
    slots: list[EventSlot] = []
    for _ in range(drama_slots):
        slots.append(EventSlot(block_type=BlockType.DRAMA))
    for _ in range(training_slots):
        slots.append(EventSlot(block_type=BlockType.TRAINING))
    slots.append(EventSlot(block_type=BlockType.PREGAME))
    for i in range(game_phases):
        slots.append(EventSlot(block_type=BlockType.GAME_PHASE, phase_index=i))
    slots.append(EventSlot(block_type=BlockType.POSTGAME))
    if include_downtime:
        slots.append(EventSlot(block_type=BlockType.DOWNTIME))
    return WeekSchedule(season=season, week=week, slots=slots)
