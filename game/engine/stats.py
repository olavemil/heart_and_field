"""Stat system — tuples, named stats, derived observables.

Three layers from design §2:
- StatTuple (deep): value/awareness/focus/weight — changes slowly, side-effect only.
- StatName (mid): the simulation variables events target.
- ObservableName (surface): computed at read-time from named stats. Never stored.
"""

from __future__ import annotations

import random as _random
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class StatName(str, Enum):
    STRENGTH = "strength"
    SPEED = "speed"
    STAMINA = "stamina"
    FINESSE = "finesse"
    CONFIDENCE = "confidence"
    INSECURITY = "insecurity"
    AGGRESSIVENESS = "aggressiveness"
    CAUTIOUSNESS = "cautiousness"
    MOTIVATION = "motivation"
    LEADERSHIP = "leadership"
    COLLABORATION = "collaboration"
    DEFENSIVENESS = "defensiveness"
    INTROSPECTION = "introspection"
    REFLECTION = "reflection"


class ObservableName(str, Enum):
    ARROGANCE = "arrogance"
    SELF_DOUBT = "self_doubt"
    COMPOSURE = "composure"
    COACHABILITY = "coachability"
    INTIMIDATION = "intimidation"
    WARMTH = "warmth"
    CHARISMA = "charisma"
    RESILIENCE = "resilience"


@dataclass
class StatTuple:
    """Per-stat psychological substrate. Tier A only."""

    value: float
    awareness: float = 0.5
    focus: float = 0.5
    weight: float = 1.0  # [-1.0, 1.0] — negative = steers against signal

    def perceived(self, rng: _random.Random | None = None) -> float:
        """What the character believes this stat is.

        Low awareness inflates the noise on self-reads.
        """
        r = rng if rng is not None else _random
        noise = (1.0 - self.awareness) * r.gauss(0.0, 0.15)
        return clamp(self.value + noise)

    def acted_on(self, signal: float) -> float:
        """Translate a perceived signal into behavioural drive."""
        return signal * self.weight

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "awareness": self.awareness,
            "focus": self.focus,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "StatTuple":
        return cls(
            value=float(d["value"]),
            awareness=float(d["awareness"]),
            focus=float(d["focus"]),
            weight=float(d.get("weight", 1.0)),
        )


# Type alias — Tier A uses StatTuple, Tier B uses float.
StatValue = float | StatTuple


def stat_value(s: StatValue) -> float:
    """Unwrap a StatTuple or pass through a flat float."""
    return s.value if isinstance(s, StatTuple) else float(s)


# --- Derived observables (design §2.4) --------------------------------------
#
# These are never stored. Compute at read-time via `observable()`.
# All formulas are [0, 1] if their inputs are [0, 1].

ObservableFormula = "callable[[Mapping[StatName, StatValue]], float]"


def _get(stats: Mapping[StatName, StatValue], name: StatName) -> float:
    return stat_value(stats[name])


OBSERVABLE_FORMULAS: dict[ObservableName, callable] = {
    ObservableName.ARROGANCE: lambda s: (
        _get(s, StatName.CONFIDENCE)
        * (1.0 - _get(s, StatName.INTROSPECTION))
        * (1.0 - _get(s, StatName.INSECURITY))
    ),
    ObservableName.SELF_DOUBT: lambda s: (
        _get(s, StatName.INSECURITY)
        * (1.0 - _get(s, StatName.CONFIDENCE))
        * _get(s, StatName.REFLECTION)
    ),
    ObservableName.COMPOSURE: lambda s: (
        (1.0 - _get(s, StatName.AGGRESSIVENESS))
        * _get(s, StatName.CAUTIOUSNESS)
        * (1.0 - _get(s, StatName.INSECURITY))
    ),
    ObservableName.COACHABILITY: lambda s: (
        _get(s, StatName.REFLECTION)
        * _get(s, StatName.INTROSPECTION)
        * (1.0 - _get(s, StatName.DEFENSIVENESS))
    ),
    ObservableName.INTIMIDATION: lambda s: (
        _get(s, StatName.AGGRESSIVENESS)
        * _get(s, StatName.CONFIDENCE)
        * _get(s, StatName.STRENGTH)
    ),
    ObservableName.WARMTH: lambda s: (
        _get(s, StatName.COLLABORATION)
        * (1.0 - _get(s, StatName.DEFENSIVENESS))
        * (1.0 - _get(s, StatName.AGGRESSIVENESS))
    ),
    ObservableName.CHARISMA: lambda s: (
        _get(s, StatName.LEADERSHIP)
        * _get(s, StatName.CONFIDENCE)
        * (1.0 - _get(s, StatName.CAUTIOUSNESS))
    ),
    ObservableName.RESILIENCE: lambda s: (
        _get(s, StatName.STAMINA)
        * (1.0 - _get(s, StatName.INSECURITY))
        * _get(s, StatName.MOTIVATION)
    ),
}


def compute_observable(
    stats: Mapping[StatName, StatValue], obs: ObservableName
) -> float:
    return clamp(OBSERVABLE_FORMULAS[obs](stats))
