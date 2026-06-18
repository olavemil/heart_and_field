"""Outcome records — the narrative memory (design §7.3, technical §3.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from .event_taxonomy import EventId


@dataclass(frozen=True)
class WeekPhase:
    """A point in simulated time. Season:week:phase.

    phase = -1 for non-game moments (drama, pregame, postgame).
    """

    season: int
    week: int
    phase: int = -1

    def to_dict(self) -> dict:
        return {"season": self.season, "week": self.week, "phase": self.phase}

    @classmethod
    def from_dict(cls, d: Mapping) -> "WeekPhase":
        return cls(
            season=int(d["season"]),
            week=int(d["week"]),
            phase=int(d.get("phase", -1)),
        )


@dataclass
class OutcomeRecord:
    event_id: str
    timestamp: WeekPhase
    participants: dict[str, str]  # role -> character id
    branch_taken: str
    summary: str  # authored, embeddable string
    arc_summary: str | None = None  # accumulated digest if carries_arc_context
    stat_deltas: dict[str, dict[str, float]] = field(default_factory=dict)
    flags: set[str] = field(default_factory=set)
    # Canonical EventId triple from the blueprint, when set. Used by
    # chain bias logic to look up outgoing edges.
    taxonomy_id: "EventId | None" = None
    # Absolute calendar day this outcome resolved on (``WorldClock
    # .day_ordinal``; week 1 Monday == 0). ``WeekPhase`` only tracks the
    # week, so this is what lets the arc-recap beat tell that a thread
    # last advanced on an earlier day. ``None`` on legacy saves.
    day_ordinal: int | None = None
    # The player stance resolved for this event (``PlayerStance`` value).
    # Stored so the next event can bias toward continuity ("role in the
    # prior event"). ``None`` on legacy saves / non-stance flows.
    player_stance: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "event_id": self.event_id,
            "timestamp": self.timestamp.to_dict(),
            "participants": dict(self.participants),
            "branch_taken": self.branch_taken,
            "summary": self.summary,
            "arc_summary": self.arc_summary,
            "stat_deltas": {
                cid: dict(deltas) for cid, deltas in self.stat_deltas.items()
            },
            "flags": sorted(self.flags),
        }
        if self.taxonomy_id is not None:
            d["taxonomy_id"] = self.taxonomy_id.to_dict()
        if self.day_ordinal is not None:
            d["day_ordinal"] = self.day_ordinal
        if self.player_stance is not None:
            d["player_stance"] = self.player_stance
        return d

    @classmethod
    def from_dict(cls, d: Mapping) -> "OutcomeRecord":
        from .event_taxonomy import EventId

        tid = d.get("taxonomy_id")
        return cls(
            event_id=d["event_id"],
            timestamp=WeekPhase.from_dict(d["timestamp"]),
            participants=dict(d.get("participants", {})),
            branch_taken=d["branch_taken"],
            summary=d["summary"],
            arc_summary=d.get("arc_summary"),
            stat_deltas={
                cid: dict(deltas)
                for cid, deltas in d.get("stat_deltas", {}).items()
            },
            flags=set(d.get("flags", [])),
            taxonomy_id=EventId.from_dict(tid) if tid is not None else None,
            day_ordinal=d.get("day_ordinal"),
            player_stance=d.get("player_stance"),
        )
