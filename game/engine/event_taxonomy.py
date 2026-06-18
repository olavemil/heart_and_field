"""Event dimensions and chain edges (addendum §4.3–§4.5; reshaped ADR-001).

``EventType`` composes the three dimensions, but its **identity is the
essence ``(domain, nature)``** — the categorical kind of event, used for
chaining and the "valid combinations" registry. Tone is *not* part of
identity: an ``EventType`` carries the ``possible_tones`` it can serve,
and only the *resolved* tone matters at a continuation boundary. Many
blueprints may share one ``EventType`` (``blueprint.id`` is the real key).

Chain edges (``EventChainEdge``) declare how one essence leads to another
along a shared dimension (scene continuity, same nature, same domain, or
scene-graph adjacency). The chain table is small; content authors extend
it as they build out the event library.
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
# EventType
# ===========================================================================


# EventTone declaration order — the deterministic tiebreak for picking a
# representative tone from a set (see ``EventType.tone``).
def _representative_tone(tones: "frozenset[EventTone]") -> "EventTone | None":
    for t in EventTone:
        if t in tones:
            return t
    return None


@dataclass(frozen=True)
class EventType:
    """Categorical event type — ``(domain, nature, possible_tones)`` (ADR-001).

    **Identity is all three** (natural equality): two event types differ
    if their tone sets differ — ``(invitation, sport, {hostile,
    melancholy})`` is not the same type as ``(invitation, sport,
    {romantic, warm})``. ``possible_tones`` is a *type-level* property
    (which tones this event can take), distinct from the per-instance
    *resolved* tone that drives continuation.

    These are axes of an event's descriptor. The intended continuation
    model (ADR-001) treats ``(domain, nature, tone, time, location)`` as a
    state vector and generates follow-ups by perturbing a subset of axes —
    no single 2-tuple "essence" is privileged. ``key()`` exposes a coarse
    ``(domain, nature)`` label only for the *interim* registry/chain
    scaffolding (``VALID_EVENT_COMBINATIONS``, ``chains_from``), which the
    dimensional continuation engine will supersede.

    Not a primary key: ``blueprint.id`` identifies a blueprint; many
    blueprints may share one ``EventType`` (→ weighted selection).

    ``tone`` is a transition-era convenience (excluded from identity).
    Authors may still pass a single ``tone=`` (it populates
    ``possible_tones``); ``.tone`` exposes a representative tone for code
    that still reads a single value (figure posture/proximity, scene
    intro) until the tone resolver lands. Passing ``possible_tones=``
    directly is the forward form.
    """

    # Field order preserves back-compat positional/keyword use
    # (``EventType(nature, domain, tone)``). ``tone`` is the derived
    # representative bridge and is excluded from identity; ``possible_tones``
    # IS part of identity.
    nature: EventNature
    domain: EventDomain
    tone: EventTone | None = field(default=None, compare=False)
    possible_tones: frozenset[EventTone] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        tones = self.possible_tones
        if not isinstance(tones, frozenset):
            tones = frozenset(tones)
        if not tones and self.tone is not None:
            tones = frozenset({self.tone})
        object.__setattr__(self, "possible_tones", tones)
        # Representative single tone (deterministic; the authored one in the
        # single-tone case). Bridges code still reading a scalar tone.
        if self.tone is None:
            object.__setattr__(self, "tone", _representative_tone(tones))

    def key(self) -> str:
        """Coarse ``{domain}_{nature}`` label for the interim registry /
        coverage checks — NOT the identity (see ``to_dict``)."""
        return f"{self.domain.value}_{self.nature.value}"

    def to_dict(self) -> dict:
        return {
            "domain": self.domain.value,
            "nature": self.nature.value,
            "possible_tones": sorted(t.value for t in self.possible_tones),
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "EventType":
        if d.get("possible_tones") is not None:
            tones = frozenset(EventTone(t) for t in d["possible_tones"])
        elif d.get("tone") is not None:  # legacy single-tone saves
            tones = frozenset({EventTone(d["tone"])})
        else:
            tones = frozenset()
        return cls(
            domain=EventDomain(d["domain"]),
            nature=EventNature(d["nature"]),
            possible_tones=tones,
        )

    @classmethod
    def from_key(cls, key: str) -> "EventType":
        """Parse an essence key (``{domain}_{nature}``) back into an
        ``EventType`` with an empty tone set."""
        parts = key.split("_", 1)
        if len(parts) != 2:
            raise ValueError(f"invalid event key: {key!r}")
        return cls(domain=EventDomain(parts[0]), nature=EventNature(parts[1]))


# ===========================================================================
# Tone resolution (Phase 25.2)
# ===========================================================================
#
# The per-instance resolved tone is sampled from an EventType's
# ``possible_tones`` — biased toward the tone carried from the prior event
# (continuity) and toward a context-derived target mood (morale/momentum),
# with chance as the tiebreak. This is the tone axis of the eventual
# dimensional continuation model; for now it just colours a single event.
#
# Standalone for now (one consumer). When dynamic participant roles land,
# the shared weighting shape will be extracted into a generic helper.

# Rough affective valence per tone, on [-1, 1]. Used to (a) pull the
# resolved tone toward a context target and (b) judge tone "adjacency"
# for carrying continuity onto a near-by available tone.
TONE_VALENCE: dict[EventTone, float] = {
    EventTone.HOSTILE: -1.0,
    EventTone.TENSE: -0.5,
    EventTone.MELANCHOLY: -0.4,
    EventTone.NEUTRAL: 0.0,
    EventTone.ROMANTIC: 0.3,
    EventTone.PLAYFUL: 0.5,
    EventTone.WARM: 0.6,
    EventTone.TRIUMPHANT: 1.0,
}

_TONE_PERSIST = 1.8       # carried tone is itself available
_TONE_ADJACENT = 1.3      # carried tone is valence-close to an available tone
_TONE_ADJ_BAND = 0.3      # |valence diff| within this counts as adjacent
_TONE_CONTEXT_W = 0.8     # how strongly context pulls toward the target mood


def resolve_event_tone(
    event_type: EventType,
    *,
    rng,
    carried_tone: EventTone | None = None,
    morale: float = 0.0,
    momentum: float = 0.0,
) -> EventTone:
    """Resolve a single tone for one firing of ``event_type``.

    Samples from ``event_type.possible_tones`` (falling back to
    ``NEUTRAL`` when none are declared), weighting each candidate by:

    - **continuity** — the ``carried_tone`` from the prior event is
      boosted when available, or a valence-adjacent candidate is mildly
      boosted, so a thread keeps its mood unless something shifts it;
    - **context** — candidates whose valence is near a target mood
      (derived from ``morale`` + ``momentum``) are boosted, so a bruising
      loss darkens and a surge warms;
    - **chance** — weighted-sampled with the injected ``rng``.

    A single-tone (or empty) type resolves deterministically. Pure +
    rng-injected; never raises.
    """
    # Deterministic order so sampling is reproducible (frozenset order
    # is not stable).
    candidates = sorted(
        event_type.possible_tones, key=lambda t: (TONE_VALENCE.get(t, 0.0), t.value)
    )
    if not candidates:
        return EventTone.NEUTRAL
    if len(candidates) == 1:
        return candidates[0]

    target = max(-1.0, min(1.0, 0.5 * morale + 0.5 * momentum))
    carried_v = (
        TONE_VALENCE.get(carried_tone) if carried_tone is not None else None
    )

    weights: list[float] = []
    for t in candidates:
        v = TONE_VALENCE.get(t, 0.0)
        w = 1.0 + _TONE_CONTEXT_W * (1.0 - abs(v - target) / 2.0)
        if carried_tone is not None:
            if t == carried_tone:
                w *= _TONE_PERSIST
            elif carried_v is not None and abs(v - carried_v) <= _TONE_ADJ_BAND:
                w *= _TONE_ADJACENT
        weights.append(w)

    total = sum(weights)
    if total <= 0:
        return candidates[0]
    roll = rng.random() * total
    acc = 0.0
    for t, w in zip(candidates, weights):
        acc += w
        if roll <= acc:
            return t
    return candidates[-1]


# ===========================================================================
# Valid event combinations (addendum §4.4)
# ===========================================================================
#
# Authored allowlist — only these (domain, nature, tone) combos have
# blueprints. ``is_valid_event_id`` checks membership; content authors
# can extend the table as the event library grows.


def _valid(domain: EventDomain, nature: EventNature, tone: EventTone) -> EventType:
    return EventType(nature=nature, domain=domain, tone=tone)


VALID_EVENT_COMBINATIONS: frozenset[EventType] = frozenset({
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


def is_valid_event_id(event_id: EventType) -> bool:
    """``True`` when ``event_id`` is in the authored event list.

    INTERIM scaffolding (Phase 17). The dimensional continuation model
    (ADR-001) generates follow-ups by perturbing the event state vector,
    so a hard validity registry becomes a loose authoring/coverage aid
    rather than a gate. Left as exact membership while content is
    single-tone; revisited when the continuation engine lands.
    """
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

    from_id: EventType
    to_id: EventType
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
            from_id=EventType.from_dict(d["from_id"]),
            to_id=EventType.from_dict(d["to_id"]),
            dimension=ChainDimension(d["dimension"]),
            condition=d.get("condition"),
        )


# Representative chain table from addendum §4.5. Authors extend.
def _chain(
    from_id: EventType, to_id: EventType,
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
    event_id: EventType,
    *,
    dimensions: frozenset[ChainDimension] | None = None,
) -> list[EventChainEdge]:
    """Return chain edges originating at ``event_id``. Optional
    ``dimensions`` filter restricts to a subset (e.g. only SCENE
    edges when staying in the same room).

    INTERIM scaffolding (Phase 17): the dimensional continuation engine
    (ADR-001) will replace authored edge-matching with state-vector
    perturbation + per-axis compatibility. Exact ``==`` holds while
    content is single-tone.
    """
    out = [e for e in CHAIN_EDGES if e.from_id == event_id]
    if dimensions is not None:
        out = [e for e in out if e.dimension in dimensions]
    return out
