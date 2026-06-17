"""Character tiers (design §3, technical §3.2).

Tier A — full tuple per stat, full history. Player + promoted NPCs.
Tier B — named recurring. Flat stat values, no tuple.
Tier D — seed only. Attributes projected on demand, never materialised.
"""

from __future__ import annotations

import random as _random
from dataclasses import dataclass, field
from enum import Enum
from statistics import fmean
from typing import Mapping

from .motivators import Motivator
from .outcomes import OutcomeRecord
from .quirks import Quirk
from .relationships import RelationshipState
from .sprite_pool import CharacterDescriptor
from .stats import (
    ObservableName,
    StatName,
    StatTuple,
    StatValue,
    clamp,
    compute_observable,
    stat_value,
)


class CharacterRole(str, Enum):
    # Sport roles
    STRIKER = "striker"
    MIDFIELDER = "midfielder"
    DEFENDER = "defender"
    GOALKEEPER = "goalkeeper"
    # Non-playing
    MANAGER = "manager"
    ASSISTANT_COACH = "assistant_coach"
    PHYSIO = "physio"
    MEDIA = "media"
    FAMILY = "family"
    OTHER = "other"


# Roles that never take the field. The match simulation must exclude these
# from the playing squad — a manager or physio cannot be a goal scorer.
# Superset of the roles ``content/events/_helpers.teammate()`` excludes
# (which also keeps PHYSIO/ASSISTANT_COACH out of the match, where
# ``teammate()`` does not), so any scorer drawn from the playing squad is
# always a valid ``teammate()`` for in-match event casting.
NON_PLAYING_ROLES: frozenset["CharacterRole"] = frozenset(
    {
        CharacterRole.MANAGER,
        CharacterRole.ASSISTANT_COACH,
        CharacterRole.PHYSIO,
        CharacterRole.MEDIA,
        CharacterRole.FAMILY,
        CharacterRole.OTHER,
    }
)


class Disposition(str, Enum):
    CALM = "calm"
    FIERY = "fiery"
    GUARDED = "guarded"
    WARM = "warm"
    COMPETITIVE = "competitive"
    WITHDRAWN = "withdrawn"


# --- Tier D projection weights ----------------------------------------------
#
# A Tier D character is a seed; any stat value is projected on demand. These
# tables shape the projection. Keep them minimal — Tier D is scenery.

ROLE_WEIGHTS: dict[CharacterRole, dict[StatName, float]] = {
    CharacterRole.STRIKER: {
        StatName.SPEED: 1.0,
        StatName.FINESSE: 0.9,
        StatName.CONFIDENCE: 0.8,
        StatName.STRENGTH: 0.6,
        StatName.STAMINA: 0.7,
        StatName.AGGRESSIVENESS: 0.7,
    },
    CharacterRole.MIDFIELDER: {
        StatName.STAMINA: 1.0,
        StatName.FINESSE: 0.9,
        StatName.SPEED: 0.7,
        StatName.COLLABORATION: 0.8,
        StatName.LEADERSHIP: 0.6,
    },
    CharacterRole.DEFENDER: {
        StatName.STRENGTH: 1.0,
        StatName.CAUTIOUSNESS: 0.8,
        StatName.STAMINA: 0.8,
        StatName.COLLABORATION: 0.7,
        StatName.SPEED: 0.5,
    },
    CharacterRole.GOALKEEPER: {
        StatName.FINESSE: 0.9,
        StatName.CAUTIOUSNESS: 0.9,
        StatName.CONFIDENCE: 0.8,
        StatName.STRENGTH: 0.5,
    },
}

# Dispositions nudge personality-adjacent stats. Additive on top of role projection.
DISPOSITION_WEIGHTS: dict[Disposition, dict[StatName, float]] = {
    Disposition.CALM: {
        StatName.CAUTIOUSNESS: 0.15,
        StatName.AGGRESSIVENESS: -0.15,
    },
    Disposition.FIERY: {
        StatName.AGGRESSIVENESS: 0.2,
        StatName.CAUTIOUSNESS: -0.15,
        StatName.CONFIDENCE: 0.1,
    },
    Disposition.GUARDED: {
        StatName.DEFENSIVENESS: 0.2,
        StatName.COLLABORATION: -0.1,
    },
    Disposition.WARM: {
        StatName.COLLABORATION: 0.2,
        StatName.DEFENSIVENESS: -0.1,
    },
    Disposition.COMPETITIVE: {
        StatName.MOTIVATION: 0.2,
        StatName.AGGRESSIVENESS: 0.1,
    },
    Disposition.WITHDRAWN: {
        StatName.COLLABORATION: -0.15,
        StatName.INSECURITY: 0.15,
    },
}


# --- Tier D ------------------------------------------------------------------


@dataclass
class TierDSeed:
    """Minimal seed for ad-hoc characters. Never materialised into full state."""

    role: CharacterRole
    skill_rating: float  # [0, 1]
    form_trend: float = 0.0  # [-1, 1]
    disposition: Disposition = Disposition.CALM

    def project(
        self, stat: StatName, rng: _random.Random | None = None
    ) -> float:
        """Derive a stat value on demand from the seed."""
        r = rng if rng is not None else _random
        role_w = ROLE_WEIGHTS.get(self.role, {}).get(stat, 0.5)
        base = self.skill_rating * role_w
        disp = DISPOSITION_WEIGHTS.get(self.disposition, {}).get(stat, 0.0)
        # Form trend nudges confidence / motivation specifically.
        form = 0.0
        if stat in (StatName.CONFIDENCE, StatName.MOTIVATION):
            form = self.form_trend * 0.15
        noise = r.gauss(0.0, 0.05)
        return clamp(base + disp + form + noise)

    def to_dict(self) -> dict:
        return {
            "role": self.role.value,
            "skill_rating": self.skill_rating,
            "form_trend": self.form_trend,
            "disposition": self.disposition.value,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "TierDSeed":
        return cls(
            role=CharacterRole(d["role"]),
            skill_rating=float(d["skill_rating"]),
            form_trend=float(d.get("form_trend", 0.0)),
            disposition=Disposition(
                d.get("disposition", Disposition.CALM.value)
            ),
        )


# --- Tier B ------------------------------------------------------------------


@dataclass
class TierBCharacter:
    """Named recurring character. Flat stat values, no tuple."""

    id: str
    name: str
    role: CharacterRole
    stats: dict[StatName, float] = field(default_factory=dict)
    motivators: list[Motivator] = field(default_factory=list)
    relationships: dict[str, RelationshipState] = field(default_factory=dict)
    nickname: str | None = None
    quirks: list[Quirk] = field(default_factory=list)
    gender_presentation: str = "masculine"
    # Visual appearance axes (skin, hair, age, build) for consistent
    # figure-asset selection across scenes. None for characters created
    # before the figure pipeline (legacy/test). See field_assets design.
    descriptor: CharacterDescriptor | None = None

    def observable(self, obs: ObservableName) -> float:
        return compute_observable(self.stats, obs)

    def to_dict(self) -> dict:
        return {
            "tier": "B",
            "id": self.id,
            "name": self.name,
            "nickname": self.nickname,
            "role": self.role.value,
            "gender_presentation": self.gender_presentation,
            "stats": {s.value: v for s, v in self.stats.items()},
            "motivators": [m.to_dict() for m in self.motivators],
            "relationships": {
                cid: rs.to_dict() for cid, rs in self.relationships.items()
            },
            "quirks": [q.to_dict() for q in self.quirks],
            "descriptor": self.descriptor.to_dict() if self.descriptor else None,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "TierBCharacter":
        return cls(
            id=d["id"],
            name=d["name"],
            nickname=d.get("nickname"),
            role=CharacterRole(d["role"]),
            stats={StatName(k): float(v) for k, v in d.get("stats", {}).items()},
            motivators=[Motivator.from_dict(m) for m in d.get("motivators", [])],
            relationships={
                cid: RelationshipState.from_dict(rs)
                for cid, rs in d.get("relationships", {}).items()
            },
            quirks=[Quirk.from_dict(q) for q in d.get("quirks", [])],
            gender_presentation=str(d.get("gender_presentation", "masculine")),
            descriptor=(
                CharacterDescriptor.from_dict(d["descriptor"])
                if d.get("descriptor")
                else None
            ),
        )


# --- Tier A ------------------------------------------------------------------


@dataclass
class TierACharacter:
    """Full character — tuple per stat, full event history."""

    id: str
    name: str
    role: CharacterRole
    stats: dict[StatName, StatTuple] = field(default_factory=dict)
    motivators: list[Motivator] = field(default_factory=list)
    relationships: dict[str, RelationshipState] = field(default_factory=dict)
    event_history: list[OutcomeRecord] = field(default_factory=list)
    nickname: str | None = None
    quirks: list[Quirk] = field(default_factory=list)
    # Per-quirk visibility hooks. Indexed by ``Quirk.key()`` — characters
    # without entries here treat all their quirks as ``VISIBLE``.
    quirk_reveals: dict[str, "QuirkReveal"] = field(default_factory=dict)
    gender_presentation: str = "masculine"
    # Visual appearance axes for consistent figure-asset selection.
    descriptor: CharacterDescriptor | None = None

    def observable(self, obs: ObservableName) -> float:
        return compute_observable(self.stats, obs)

    def insecurity(self, stat: StatName | None = None) -> float:
        """Per-stat insecurity or mean across all stats.

        Insecurity is not stored — it falls out of focus × (1 - awareness).
        """
        if stat is not None:
            t = self.stats[stat]
            return t.focus * (1.0 - t.awareness)
        if not self.stats:
            return 0.0
        return fmean(
            t.focus * (1.0 - t.awareness) for t in self.stats.values()
        )

    def to_dict(self) -> dict:
        return {
            "tier": "A",
            "id": self.id,
            "name": self.name,
            "nickname": self.nickname,
            "role": self.role.value,
            "gender_presentation": self.gender_presentation,
            "stats": {s.value: t.to_dict() for s, t in self.stats.items()},
            "motivators": [m.to_dict() for m in self.motivators],
            "relationships": {
                cid: rs.to_dict() for cid, rs in self.relationships.items()
            },
            "event_history": [o.to_dict() for o in self.event_history],
            "quirks": [q.to_dict() for q in self.quirks],
            "quirk_reveals": {
                k: r.to_dict() for k, r in self.quirk_reveals.items()
            },
            "descriptor": self.descriptor.to_dict() if self.descriptor else None,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "TierACharacter":
        from .quirks import QuirkReveal

        return cls(
            id=d["id"],
            name=d["name"],
            nickname=d.get("nickname"),
            role=CharacterRole(d["role"]),
            stats={
                StatName(k): StatTuple.from_dict(v)
                for k, v in d.get("stats", {}).items()
            },
            motivators=[Motivator.from_dict(m) for m in d.get("motivators", [])],
            relationships={
                cid: RelationshipState.from_dict(rs)
                for cid, rs in d.get("relationships", {}).items()
            },
            event_history=[
                OutcomeRecord.from_dict(o) for o in d.get("event_history", [])
            ],
            quirks=[Quirk.from_dict(q) for q in d.get("quirks", [])],
            quirk_reveals={
                k: QuirkReveal.from_dict(r)
                for k, r in d.get("quirk_reveals", {}).items()
            },
            gender_presentation=str(d.get("gender_presentation", "masculine")),
            descriptor=(
                CharacterDescriptor.from_dict(d["descriptor"])
                if d.get("descriptor")
                else None
            ),
        )


Character = TierACharacter | TierBCharacter


def character_stat(
    character: Character, stat: StatName
) -> float:
    """Unwrap a character's stat — tuple.value for Tier A, float for Tier B."""
    raw = character.stats.get(stat)
    if raw is None:
        return 0.0
    return stat_value(raw)
