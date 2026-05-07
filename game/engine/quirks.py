"""Quirk system (addendum §2).

A quirk is a two-dimensional tag — ``(domain, pattern)`` — that captures
*which area of life* a character behaves unusually in (domain) and
*what shape* the behaviour takes (pattern). All downstream effects
(stat shifts, relationship affinity, event-weight bias, visibility) are
derived from the pair via lookup tables; **no per-quirk authoring is
needed beyond picking the pair**.

This module is pure data + pure functions: no RNG, no I/O. Integration
with character casts and event selection lives at the call site.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping

from .stats import StatName


# ---------------------------------------------------------------------------
# Dimensions (addendum §2.1)
# ---------------------------------------------------------------------------


class QuirkDomain(str, Enum):
    PERFORMANCE = "performance"  # training, match execution
    SOCIAL = "social"            # relationships, group dynamics
    EMOTIONAL = "emotional"      # stress response, mood regulation
    COGNITIVE = "cognitive"      # decision-making, pattern recognition
    PHYSICAL = "physical"        # body, appearance, health habits


class QuirkPattern(str, Enum):
    COMPULSIVE = "compulsive"     # repeats behaviour beyond usefulness
    AVOIDANT = "avoidant"         # systematically sidesteps something
    SEEKING = "seeking"           # actively pursues something
    REACTIVE = "reactive"         # strong response to specific triggers
    RIGID = "rigid"               # resistant to change in this domain
    PERFORMATIVE = "performative" # behaves differently when observed


@dataclass(frozen=True)
class Quirk:
    """A character quirk. Equality / hashing keys on ``(domain, pattern)``
    so duplicate quirks on the same character are de-dupable via a set."""

    domain: QuirkDomain
    pattern: QuirkPattern

    def key(self) -> tuple[QuirkDomain, QuirkPattern]:
        return (self.domain, self.pattern)

    def to_dict(self) -> dict:
        return {"domain": self.domain.value, "pattern": self.pattern.value}

    @classmethod
    def from_dict(cls, d: Mapping) -> "Quirk":
        return cls(
            domain=QuirkDomain(d["domain"]),
            pattern=QuirkPattern(d["pattern"]),
        )


# ---------------------------------------------------------------------------
# Visibility (addendum §2.2)
# ---------------------------------------------------------------------------


class QuirkVisibility(str, Enum):
    VISIBLE = "visible"      # apparent immediately
    INFERABLE = "inferable"  # emerges under mild pressure
    HIDDEN = "hidden"        # only surfaces under specific conditions


@dataclass
class QuirkReveal:
    """How a specific character's quirk surfaces to observers.

    ``reveal_event_tags`` lists event tags that, when seen, expose this
    quirk to observers. ``reveal_familiarity`` is an alternative
    threshold: relationships above the threshold also expose it.
    """

    quirk: Quirk
    visibility: QuirkVisibility = QuirkVisibility.VISIBLE
    reveal_event_tags: list[str] = field(default_factory=list)
    reveal_familiarity: float | None = None

    def to_dict(self) -> dict:
        return {
            "quirk": self.quirk.to_dict(),
            "visibility": self.visibility.value,
            "reveal_event_tags": list(self.reveal_event_tags),
            "reveal_familiarity": self.reveal_familiarity,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "QuirkReveal":
        rf = d.get("reveal_familiarity")
        return cls(
            quirk=Quirk.from_dict(d["quirk"]),
            visibility=QuirkVisibility(d.get("visibility", QuirkVisibility.VISIBLE.value)),
            reveal_event_tags=list(d.get("reveal_event_tags", [])),
            reveal_familiarity=float(rf) if rf is not None else None,
        )


def visible_to_observer(
    reveal: QuirkReveal,
    *,
    observer_familiarity: float = 0.0,
    witnessed_event_tags: Iterable[str] = (),
) -> bool:
    """Is the quirk currently visible to this observer?

    - ``VISIBLE`` quirks are always visible.
    - ``INFERABLE`` and ``HIDDEN`` quirks become visible when the
      observer's familiarity crosses ``reveal_familiarity`` *or* when a
      witnessed event matches one of ``reveal_event_tags``.
    - HIDDEN quirks otherwise stay hidden.
    """
    if reveal.visibility == QuirkVisibility.VISIBLE:
        return True
    witnessed = set(witnessed_event_tags)
    if witnessed & set(reveal.reveal_event_tags):
        return True
    if (
        reveal.reveal_familiarity is not None
        and observer_familiarity >= reveal.reveal_familiarity
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Affinity / friction (addendum §2.3)
# ---------------------------------------------------------------------------


# Quirk pairs that work well together. Keys and values are
# ``(domain, pattern)`` tuples. The relation is treated as undirected
# at lookup time — :func:`has_affinity` checks both orderings.
QUIRK_AFFINITIES: dict[
    tuple[QuirkDomain, QuirkPattern],
    list[tuple[QuirkDomain, QuirkPattern]],
] = {
    (QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING): [
        (QuirkDomain.PERFORMANCE, QuirkPattern.COMPULSIVE),
        (QuirkDomain.SOCIAL, QuirkPattern.SEEKING),
    ],
    (QuirkDomain.SOCIAL, QuirkPattern.SEEKING): [
        (QuirkDomain.EMOTIONAL, QuirkPattern.REACTIVE),
        (QuirkDomain.SOCIAL, QuirkPattern.PERFORMATIVE),
    ],
    (QuirkDomain.COGNITIVE, QuirkPattern.RIGID): [
        (QuirkDomain.PERFORMANCE, QuirkPattern.COMPULSIVE),
    ],
    (QuirkDomain.PHYSICAL, QuirkPattern.SEEKING): [
        (QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING),
    ],
}


# Quirk pairs that generate conflict events. Same shape as affinities.
QUIRK_FRICTIONS: dict[
    tuple[QuirkDomain, QuirkPattern],
    list[tuple[QuirkDomain, QuirkPattern]],
] = {
    (QuirkDomain.COGNITIVE, QuirkPattern.RIGID): [
        (QuirkDomain.COGNITIVE, QuirkPattern.AVOIDANT),
        (QuirkDomain.SOCIAL, QuirkPattern.SEEKING),
    ],
    (QuirkDomain.PERFORMANCE, QuirkPattern.PERFORMATIVE): [
        (QuirkDomain.PERFORMANCE, QuirkPattern.AVOIDANT),
    ],
    (QuirkDomain.EMOTIONAL, QuirkPattern.REACTIVE): [
        (QuirkDomain.SOCIAL, QuirkPattern.RIGID),
    ],
    (QuirkDomain.SOCIAL, QuirkPattern.AVOIDANT): [
        (QuirkDomain.SOCIAL, QuirkPattern.SEEKING),
    ],
}


def has_affinity(a: Quirk, b: Quirk) -> bool:
    """True when ``a`` and ``b`` are listed as compatible in either
    direction in :data:`QUIRK_AFFINITIES`."""
    return (
        b.key() in QUIRK_AFFINITIES.get(a.key(), ())
        or a.key() in QUIRK_AFFINITIES.get(b.key(), ())
    )


def has_friction(a: Quirk, b: Quirk) -> bool:
    """True when ``a`` and ``b`` are listed as conflicting in either
    direction in :data:`QUIRK_FRICTIONS`."""
    return (
        b.key() in QUIRK_FRICTIONS.get(a.key(), ())
        or a.key() in QUIRK_FRICTIONS.get(b.key(), ())
    )


def pairwise_affinity(
    quirks_a: Iterable[Quirk], quirks_b: Iterable[Quirk]
) -> int:
    """Count of affinity pairs across two quirk lists. Useful as a
    weight contribution when picking warm/social events."""
    qa = list(quirks_a)
    qb = list(quirks_b)
    return sum(1 for a in qa for b in qb if has_affinity(a, b))


def pairwise_friction(
    quirks_a: Iterable[Quirk], quirks_b: Iterable[Quirk]
) -> int:
    """Count of friction pairs — feeds conflict event weight."""
    qa = list(quirks_a)
    qb = list(quirks_b)
    return sum(1 for a in qa for b in qb if has_friction(a, b))


# ---------------------------------------------------------------------------
# Stat modifiers
# ---------------------------------------------------------------------------


# Per-quirk static stat deltas applied to the character's flat stat
# values (Tier B) or tuple ``value`` (Tier A) at compute time. These are
# tiny tilts — the character is *prone* to having higher confidence,
# not "always confident". Authors extend this table; missing pairs map
# to no modifier.
QUIRK_STAT_MODIFIERS: dict[
    tuple[QuirkDomain, QuirkPattern], dict[StatName, float]
] = {
    (QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING): {
        StatName.STAMINA: 0.05,
        StatName.SPEED: 0.03,
    },
    (QuirkDomain.PERFORMANCE, QuirkPattern.COMPULSIVE): {
        StatName.FINESSE: 0.05,
    },
    (QuirkDomain.PERFORMANCE, QuirkPattern.PERFORMATIVE): {
        StatName.CONFIDENCE: 0.04,
        StatName.COLLABORATION: -0.03,
    },
    (QuirkDomain.PERFORMANCE, QuirkPattern.AVOIDANT): {
        StatName.CONFIDENCE: -0.05,
    },
    (QuirkDomain.SOCIAL, QuirkPattern.SEEKING): {
        StatName.LEADERSHIP: 0.04,
        StatName.COLLABORATION: 0.03,
    },
    (QuirkDomain.SOCIAL, QuirkPattern.AVOIDANT): {
        StatName.LEADERSHIP: -0.04,
        StatName.CAUTIOUSNESS: 0.03,
    },
    (QuirkDomain.EMOTIONAL, QuirkPattern.REACTIVE): {
        StatName.CONFIDENCE: -0.03,
        StatName.INSECURITY: 0.05,
    },
    (QuirkDomain.COGNITIVE, QuirkPattern.RIGID): {
        StatName.REFLECTION: -0.03,
    },
    (QuirkDomain.COGNITIVE, QuirkPattern.COMPULSIVE): {
        StatName.REFLECTION: 0.04,
        StatName.INTROSPECTION: 0.03,
    },
    (QuirkDomain.PHYSICAL, QuirkPattern.SEEKING): {
        StatName.STAMINA: 0.04,
        StatName.STRENGTH: 0.03,
    },
}


def stat_modifier(quirk: Quirk, stat: StatName) -> float:
    """Lookup helper. Returns 0.0 when the quirk has no modifier for
    ``stat`` — additive composition without special-casing."""
    return QUIRK_STAT_MODIFIERS.get(quirk.key(), {}).get(stat, 0.0)


def total_stat_modifier(quirks: Iterable[Quirk], stat: StatName) -> float:
    """Sum of all quirks' modifiers for a stat. Multiple quirks in the
    same domain stack additively — design choice; can be capped later
    if needed."""
    return sum(stat_modifier(q, stat) for q in quirks)


# ---------------------------------------------------------------------------
# Event weight bias
# ---------------------------------------------------------------------------


# Per-quirk multipliers on event tags. Multipliers > 1 boost selection
# weight; < 1 penalise. Missing pairs map to 1.0.
QUIRK_EVENT_BIAS: dict[
    tuple[QuirkDomain, QuirkPattern], dict[str, float]
] = {
    (QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING): {
        "training": 1.5,
    },
    (QuirkDomain.PERFORMANCE, QuirkPattern.PERFORMATIVE): {
        "celebration": 1.4,
        "media": 1.3,
    },
    (QuirkDomain.PERFORMANCE, QuirkPattern.AVOIDANT): {
        "media": 0.4,
        "celebration": 0.6,
    },
    (QuirkDomain.SOCIAL, QuirkPattern.SEEKING): {
        "social": 1.4,
        "downtime": 1.3,
    },
    (QuirkDomain.SOCIAL, QuirkPattern.AVOIDANT): {
        "social": 0.5,
        "conflict": 0.6,
    },
    (QuirkDomain.EMOTIONAL, QuirkPattern.REACTIVE): {
        "vulnerability": 1.6,
        "conflict": 1.3,
    },
    (QuirkDomain.COGNITIVE, QuirkPattern.RIGID): {
        "vulnerability": 0.4,
        "training": 1.2,
    },
    (QuirkDomain.COGNITIVE, QuirkPattern.COMPULSIVE): {
        "training": 1.3,
    },
}


def event_weight_multiplier(
    quirks: Iterable[Quirk], event_tags: Iterable[str]
) -> float:
    """Compose all quirk-tag multipliers into a single multiplier.

    Multipliers compose multiplicatively across (quirk, tag) matches.
    A character with no quirks (or no matching tags) returns ``1.0``,
    so the function is safe to call unconditionally during event
    selection.
    """
    multiplier = 1.0
    tags = set(event_tags)
    for q in quirks:
        bias = QUIRK_EVENT_BIAS.get(q.key(), {})
        for tag in tags:
            if tag in bias:
                multiplier *= bias[tag]
    return multiplier


def cast_event_weight_multiplier(
    cast_quirks: Iterable[Iterable[Quirk]],
    event_tags: Iterable[str],
    *,
    friction_boost_per_pair: float = 0.25,
    affinity_boost_per_pair: float = 0.20,
) -> float:
    """Combine per-character event bias with cast-pair affinity/friction
    bumps for an event's overall selection weight.

    Conflict-tagged events get a bump per friction pair across the cast;
    warm/social events get a bump per affinity pair. The per-pair amount
    is configurable so designers can tune sensitivity without rewriting
    the table.
    """
    cast = [list(qs) for qs in cast_quirks]
    multiplier = 1.0
    tags = set(event_tags)
    for quirks in cast:
        multiplier *= event_weight_multiplier(quirks, tags)

    is_conflict = bool(tags & {"conflict", "confrontation", "rivalry"})
    is_warm = bool(tags & {"social", "celebration", "downtime", "warm"})
    if not (is_conflict or is_warm):
        return multiplier

    for i, qa in enumerate(cast):
        for qb in cast[i + 1 :]:
            if is_conflict:
                multiplier *= 1.0 + friction_boost_per_pair * pairwise_friction(qa, qb)
            if is_warm:
                multiplier *= 1.0 + affinity_boost_per_pair * pairwise_affinity(qa, qb)
    return multiplier
