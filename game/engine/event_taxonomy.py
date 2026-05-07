"""Event dimensions and chain edges (addendum §4.3–§4.5) — Phase 17.

Three independent enums compose every event id. The triple
``(domain, nature, tone)`` is the canonical key, paired with an
authored "valid combinations" registry so blueprints stay grounded in
the addendum's curated event list — no surprise combos.

Chain edges (``EventChainEdge``) declare how one event id leads to
another along a shared dimension (scene continuity, same nature,
same domain, or scene-graph adjacency). The chain table is small at
this phase; content authors extend it as they build out the event
library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


# ===========================================================================
# Three event dimensions (addendum §4.3)
# ===========================================================================


class EventNature(str, Enum):
    CONFRONTATION = "confrontation"
    ADMISSION = "admission"
    REVELATION = "revelation"
    NEGOTIATION = "negotiation"
    CELEBRATION = "celebration"
    CONSOLATION = "consolation"
    OBSERVATION = "observation"  # watching/noticing without acting
    INVITATION = "invitation"
    REJECTION = "rejection"
    COLLABORATION = "collaboration"
    COMPETITION = "competition"
    ISOLATION = "isolation"  # character alone, self-directed


class EventDomain(str, Enum):
    SPORT = "sport"
    RELATIONSHIP = "relationship"
    INSTITUTIONAL = "institutional"
    PERSONAL = "personal"
    SECRET = "secret"  # requires secret membership


class EventTone(str, Enum):
    HOSTILE = "hostile"
    TENSE = "tense"
    NEUTRAL = "neutral"
    WARM = "warm"
    ROMANTIC = "romantic"
    PLAYFUL = "playful"
    MELANCHOLY = "melancholy"
    TRIUMPHANT = "triumphant"


# ===========================================================================
# EventId
# ===========================================================================


@dataclass(frozen=True)
class EventId:
    """Three-dimensional event key.

    Frozen + hashable so it can index dicts / sets directly. ``key()``
    formats the canonical string used for blueprint ids (the format
    matches addendum §4.3: ``{domain}_{nature}_{tone}``).
    """

    nature: EventNature
    domain: EventDomain
    tone: EventTone

    def key(self) -> str:
        return f"{self.domain.value}_{self.nature.value}_{self.tone.value}"

    def to_dict(self) -> dict:
        return {
            "nature": self.nature.value,
            "domain": self.domain.value,
            "tone": self.tone.value,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "EventId":
        return cls(
            nature=EventNature(d["nature"]),
            domain=EventDomain(d["domain"]),
            tone=EventTone(d["tone"]),
        )

    @classmethod
    def from_key(cls, key: str) -> "EventId":
        """Parse a canonical key string back into an ``EventId``."""
        parts = key.split("_", 2)
        if len(parts) != 3:
            raise ValueError(f"invalid event key: {key!r}")
        return cls(
            domain=EventDomain(parts[0]),
            nature=EventNature(parts[1]),
            tone=EventTone(parts[2]),
        )


# ===========================================================================
# Valid event combinations (addendum §4.4)
# ===========================================================================
#
# Authored allowlist — only these (domain, nature, tone) combos have
# blueprints. ``is_valid_event_id`` checks membership; content authors
# can extend the table as the event library grows.


def _valid(domain: EventDomain, nature: EventNature, tone: EventTone) -> EventId:
    return EventId(nature=nature, domain=domain, tone=tone)


VALID_EVENT_COMBINATIONS: frozenset[EventId] = frozenset({
    # SPORT
    _valid(EventDomain.SPORT, EventNature.CONFRONTATION, EventTone.HOSTILE),
    _valid(EventDomain.SPORT, EventNature.CONFRONTATION, EventTone.TENSE),
    _valid(EventDomain.SPORT, EventNature.COLLABORATION, EventTone.NEUTRAL),
    _valid(EventDomain.SPORT, EventNature.COLLABORATION, EventTone.WARM),
    _valid(EventDomain.SPORT, EventNature.OBSERVATION, EventTone.NEUTRAL),
    _valid(EventDomain.SPORT, EventNature.CELEBRATION, EventTone.TRIUMPHANT),
    _valid(EventDomain.SPORT, EventNature.CONSOLATION, EventTone.MELANCHOLY),
    _valid(EventDomain.SPORT, EventNature.REVELATION, EventTone.TENSE),
    _valid(EventDomain.SPORT, EventNature.NEGOTIATION, EventTone.TENSE),
    _valid(EventDomain.SPORT, EventNature.COMPETITION, EventTone.HOSTILE),
    _valid(EventDomain.SPORT, EventNature.ISOLATION, EventTone.MELANCHOLY),
    # RELATIONSHIP
    _valid(EventDomain.RELATIONSHIP, EventNature.CONFRONTATION, EventTone.HOSTILE),
    _valid(EventDomain.RELATIONSHIP, EventNature.CONFRONTATION, EventTone.TENSE),
    _valid(EventDomain.RELATIONSHIP, EventNature.ADMISSION, EventTone.MELANCHOLY),
    _valid(EventDomain.RELATIONSHIP, EventNature.ADMISSION, EventTone.ROMANTIC),
    _valid(EventDomain.RELATIONSHIP, EventNature.REVELATION, EventTone.TENSE),
    _valid(EventDomain.RELATIONSHIP, EventNature.REVELATION, EventTone.HOSTILE),
    _valid(EventDomain.RELATIONSHIP, EventNature.INVITATION, EventTone.WARM),
    _valid(EventDomain.RELATIONSHIP, EventNature.INVITATION, EventTone.ROMANTIC),
    _valid(EventDomain.RELATIONSHIP, EventNature.REJECTION, EventTone.HOSTILE),
    _valid(EventDomain.RELATIONSHIP, EventNature.REJECTION, EventTone.MELANCHOLY),
    _valid(EventDomain.RELATIONSHIP, EventNature.CELEBRATION, EventTone.WARM),
    _valid(EventDomain.RELATIONSHIP, EventNature.CELEBRATION, EventTone.PLAYFUL),
    _valid(EventDomain.RELATIONSHIP, EventNature.CONSOLATION, EventTone.WARM),
    _valid(EventDomain.RELATIONSHIP, EventNature.CONSOLATION, EventTone.MELANCHOLY),
    _valid(EventDomain.RELATIONSHIP, EventNature.OBSERVATION, EventTone.NEUTRAL),
    _valid(EventDomain.RELATIONSHIP, EventNature.COMPETITION, EventTone.TENSE),
    _valid(EventDomain.RELATIONSHIP, EventNature.COLLABORATION, EventTone.WARM),
    _valid(EventDomain.RELATIONSHIP, EventNature.ISOLATION, EventTone.MELANCHOLY),
    _valid(EventDomain.RELATIONSHIP, EventNature.NEGOTIATION, EventTone.TENSE),
    # INSTITUTIONAL
    _valid(EventDomain.INSTITUTIONAL, EventNature.NEGOTIATION, EventTone.TENSE),
    _valid(EventDomain.INSTITUTIONAL, EventNature.NEGOTIATION, EventTone.HOSTILE),
    _valid(EventDomain.INSTITUTIONAL, EventNature.REVELATION, EventTone.TENSE),
    _valid(EventDomain.INSTITUTIONAL, EventNature.CONFRONTATION, EventTone.HOSTILE),
    _valid(EventDomain.INSTITUTIONAL, EventNature.CELEBRATION, EventTone.TRIUMPHANT),
    _valid(EventDomain.INSTITUTIONAL, EventNature.OBSERVATION, EventTone.NEUTRAL),
    _valid(EventDomain.INSTITUTIONAL, EventNature.ISOLATION, EventTone.TENSE),
    # PERSONAL
    _valid(EventDomain.PERSONAL, EventNature.ADMISSION, EventTone.MELANCHOLY),
    _valid(EventDomain.PERSONAL, EventNature.REVELATION, EventTone.TENSE),
    _valid(EventDomain.PERSONAL, EventNature.ISOLATION, EventTone.MELANCHOLY),
    _valid(EventDomain.PERSONAL, EventNature.CONSOLATION, EventTone.WARM),
    _valid(EventDomain.PERSONAL, EventNature.CELEBRATION, EventTone.WARM),
    # SECRET — require secret membership to trigger
    _valid(EventDomain.SECRET, EventNature.OBSERVATION, EventTone.NEUTRAL),
    _valid(EventDomain.SECRET, EventNature.CONFRONTATION, EventTone.TENSE),
    _valid(EventDomain.SECRET, EventNature.CONFRONTATION, EventTone.HOSTILE),
    _valid(EventDomain.SECRET, EventNature.ADMISSION, EventTone.MELANCHOLY),
    _valid(EventDomain.SECRET, EventNature.ADMISSION, EventTone.ROMANTIC),
    _valid(EventDomain.SECRET, EventNature.REVELATION, EventTone.HOSTILE),
    _valid(EventDomain.SECRET, EventNature.REVELATION, EventTone.TENSE),
    _valid(EventDomain.SECRET, EventNature.NEGOTIATION, EventTone.TENSE),
    _valid(EventDomain.SECRET, EventNature.ISOLATION, EventTone.MELANCHOLY),
})


def is_valid_event_id(event_id: EventId) -> bool:
    """``True`` when the (domain, nature, tone) triple is in the
    authored event list. Content tooling can call this to surface
    blueprint ids that no longer match the curated list."""
    return event_id in VALID_EVENT_COMBINATIONS


# ===========================================================================
# Chain edges (addendum §4.5)
# ===========================================================================


class ChainDimension(str, Enum):
    """Which dimension is shared between linked events."""

    SCENE = "scene"        # same location, tone or nature shifts
    NATURE = "nature"      # same action type, domain or tone shifts
    DOMAIN = "domain"      # same thematic space, nature shifts
    ADJACENT = "adjacent"  # scene-graph adjacency, anything shifts


@dataclass
class EventChainEdge:
    """A directed chain edge: ``from_id → to_id`` along ``dimension``.

    ``condition`` is an optional opaque string the engine evaluates at
    chain-time (e.g. ``"attraction > 0.5"`` or
    ``"observer_has_meta_secret"``). Phase 17 stores the string only;
    actual evaluation lives at the call site.
    """

    from_id: EventId
    to_id: EventId
    dimension: ChainDimension
    condition: str | None = None

    def to_dict(self) -> dict:
        return {
            "from_id": self.from_id.to_dict(),
            "to_id": self.to_id.to_dict(),
            "dimension": self.dimension.value,
            "condition": self.condition,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "EventChainEdge":
        return cls(
            from_id=EventId.from_dict(d["from_id"]),
            to_id=EventId.from_dict(d["to_id"]),
            dimension=ChainDimension(d["dimension"]),
            condition=d.get("condition"),
        )


# Representative chain table from addendum §4.5. Authors extend.
def _chain(
    from_id: EventId, to_id: EventId,
    dimension: ChainDimension, condition: str | None = None,
) -> EventChainEdge:
    return EventChainEdge(from_id, to_id, dimension, condition)


CHAIN_EDGES: list[EventChainEdge] = [
    _chain(
        _valid(EventDomain.RELATIONSHIP, EventNature.CONFRONTATION, EventTone.HOSTILE),
        _valid(EventDomain.RELATIONSHIP, EventNature.ADMISSION, EventTone.MELANCHOLY),
        ChainDimension.SCENE,
    ),
    _chain(
        _valid(EventDomain.RELATIONSHIP, EventNature.CONFRONTATION, EventTone.HOSTILE),
        _valid(EventDomain.RELATIONSHIP, EventNature.ADMISSION, EventTone.ROMANTIC),
        ChainDimension.SCENE,
        condition="attraction > 0.5",
    ),
    _chain(
        _valid(EventDomain.RELATIONSHIP, EventNature.CONFRONTATION, EventTone.TENSE),
        _valid(EventDomain.RELATIONSHIP, EventNature.NEGOTIATION, EventTone.TENSE),
        ChainDimension.SCENE,
    ),
    _chain(
        _valid(EventDomain.SPORT, EventNature.CONFRONTATION, EventTone.HOSTILE),
        _valid(EventDomain.RELATIONSHIP, EventNature.CONFRONTATION, EventTone.HOSTILE),
        ChainDimension.NATURE,
    ),
    _chain(
        _valid(EventDomain.RELATIONSHIP, EventNature.ADMISSION, EventTone.MELANCHOLY),
        _valid(EventDomain.PERSONAL, EventNature.ADMISSION, EventTone.MELANCHOLY),
        ChainDimension.NATURE,
    ),
    _chain(
        _valid(EventDomain.RELATIONSHIP, EventNature.OBSERVATION, EventTone.NEUTRAL),
        _valid(EventDomain.SECRET, EventNature.OBSERVATION, EventTone.NEUTRAL),
        ChainDimension.SCENE,
        condition="observer_has_meta_secret",
    ),
    _chain(
        _valid(EventDomain.RELATIONSHIP, EventNature.CONFRONTATION, EventTone.HOSTILE),
        _valid(EventDomain.SECRET, EventNature.CONFRONTATION, EventTone.TENSE),
        ChainDimension.SCENE,
        condition="participant_has_secret",
    ),
    _chain(
        _valid(EventDomain.SPORT, EventNature.CELEBRATION, EventTone.TRIUMPHANT),
        _valid(EventDomain.RELATIONSHIP, EventNature.CELEBRATION, EventTone.PLAYFUL),
        ChainDimension.ADJACENT,
    ),
    _chain(
        _valid(EventDomain.RELATIONSHIP, EventNature.REJECTION, EventTone.MELANCHOLY),
        _valid(EventDomain.RELATIONSHIP, EventNature.ISOLATION, EventTone.MELANCHOLY),
        ChainDimension.ADJACENT,
    ),
]


def chains_from(
    event_id: EventId,
    *,
    dimensions: frozenset[ChainDimension] | None = None,
) -> list[EventChainEdge]:
    """Return chain edges originating at ``event_id``. Optional
    ``dimensions`` filter restricts to a subset (e.g. only SCENE
    edges when staying in the same room)."""
    out = [e for e in CHAIN_EDGES if e.from_id == event_id]
    if dimensions is not None:
        out = [e for e in out if e.dimension in dimensions]
    return out
