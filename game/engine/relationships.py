"""Relationship state between two characters (design §4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class RelationshipDynamic(str, Enum):
    ACQUAINTANCE = "acquaintance"
    FRIEND = "friend"
    MENTOR = "mentor"
    RIVAL = "rival"
    ROMANTIC = "romantic"
    ANTAGONIST = "antagonist"


@dataclass
class RelationshipState:
    familiarity: float = 0.0
    trust: float = 0.5
    tension: float = 0.0
    attraction: float = 0.0
    dynamic: RelationshipDynamic = RelationshipDynamic.ACQUAINTANCE
    hidden_flags: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "familiarity": self.familiarity,
            "trust": self.trust,
            "tension": self.tension,
            "attraction": self.attraction,
            "dynamic": self.dynamic.value,
            "hidden_flags": sorted(self.hidden_flags),
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "RelationshipState":
        return cls(
            familiarity=float(d.get("familiarity", 0.0)),
            trust=float(d.get("trust", 0.5)),
            tension=float(d.get("tension", 0.0)),
            attraction=float(d.get("attraction", 0.0)),
            dynamic=RelationshipDynamic(
                d.get("dynamic", RelationshipDynamic.ACQUAINTANCE.value)
            ),
            hidden_flags=set(d.get("hidden_flags", [])),
        )
