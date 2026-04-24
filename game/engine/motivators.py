"""Motivator overlays — temporary stat modifiers (design §2.5).

Motivators shift output without touching the underlying stat. They decay
over time or on trigger events. High focus slows decay; negative tuple
weight can invert them (handled at the character layer, not here).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .stats import StatName


class MotivatorSource(str, Enum):
    COMPLIMENT = "compliment"
    CROWD = "crowd"
    PAYMENT = "payment"
    RIVALRY = "rivalry"
    CRITICISM = "criticism"
    FAMILY = "family"
    MEDIA = "media"


@dataclass
class Motivator:
    target_stat: StatName
    delta: float
    decay_rate: float  # per phase or per scene
    source: MotivatorSource
    salience: float = 1.0  # higher = slower decay

    def current_value(self, phases_elapsed: int) -> float:
        if self.salience <= 0:
            return 0.0
        return self.delta * (1.0 - self.decay_rate) ** (
            phases_elapsed / self.salience
        )

    def to_dict(self) -> dict:
        return {
            "target_stat": self.target_stat.value,
            "delta": self.delta,
            "decay_rate": self.decay_rate,
            "source": self.source.value,
            "salience": self.salience,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "Motivator":
        return cls(
            target_stat=StatName(d["target_stat"]),
            delta=float(d["delta"]),
            decay_rate=float(d["decay_rate"]),
            source=MotivatorSource(d["source"]),
            salience=float(d.get("salience", 1.0)),
        )
