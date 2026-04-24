"""Outcome records — the narrative memory (design §7.3, technical §3.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


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

    def to_dict(self) -> dict:
        return {
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

    @classmethod
    def from_dict(cls, d: Mapping) -> "OutcomeRecord":
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
        )
