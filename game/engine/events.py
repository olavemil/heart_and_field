"""Event system — blueprints, casting, selection, resolution (technical §5).

Events are authored as `EventBlueprint` records loaded from `content/events/`.
Each blueprint describes:
- its thematic tags and role slots (who can play which part),
- its scene blocks (narrative structure, branch graph),
- its prereqs / unlocks / disables in the arc graph,
- its selection weight rules,
- authored outcome-summary strings per branch.

Narration is deferred to Phase 4. Phase 3 delivers:
- eligibility + casting,
- weighted selection (with clock contributions + recency penalty),
- outcome resolution producing `OutcomeRecord` with stat deltas and summary.
"""

from __future__ import annotations

import random as _random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Mapping, Sequence

from .characters import Character, TierACharacter, TierBCharacter
from .clock import Weekday, WorldClock
from .outcomes import OutcomeRecord, WeekPhase
from .stats import StatName


def _default_clock() -> "WorldClock":
    """Factory used by ``GameState.clock`` — Monday 08:00 of week 1."""
    return WorldClock(week=1, weekday=Weekday.MON, hour=8, minute=0)



# --- Filters & weight rules --------------------------------------------------


# A cast filter accepts a character and returns True if it's eligible for the
# given role. Filters are authored as plain callables so content files can
# define them as closures over threshold values.
CastFilter = Callable[[Character], bool]


@dataclass
class RoleSlot:
    role: str  # e.g. "aggressor", "mediator", "witness"
    filter: CastFilter | None = None
    optional: bool = False


@dataclass
class WeightRule:
    """A single multiplicative factor applied to an event's selection weight.

    `predicate` inspects the (context, state) tuple and returns a float. The
    caller multiplies this into the running weight.
    """

    predicate: Callable[["GameContext", "GameState"], float]
    description: str = ""


# --- Scene structure ---------------------------------------------------------


@dataclass
class ChoiceNode:
    """Player-facing choice inside a scene block.

    Narrative template references are resolved in Phase 4; for now this is
    authored metadata that the resolution layer will consume.
    """

    prompt: str
    options: dict[str, str] = field(default_factory=dict)  # choice_id -> label


@dataclass
class SceneBlock:
    id: str
    templates: list[str] = field(default_factory=list)  # template ids (Phase 4)
    choice: ChoiceNode | None = None
    branch: dict[str, str] = field(default_factory=dict)  # choice -> next block


@dataclass
class LocationCue:
    """Where an event takes place — drives background lookup.

    Three modes:

    - ``graph_id`` set → marquee location, always the same instance
      (e.g. ``"player_home"``). The graph persists across events.
    - ``graph_id`` unset → ad-hoc location, a fresh graph is created
      each time the event runs (and closed after, so the next ad-hoc
      run gets new visuals or adopts a pool entry).
    - ``location: None`` on the blueprint → no background lookup.

    For ad-hoc graphs, ``descriptor_overrides`` lets the event nudge the
    style (e.g. force MoodTone.WARM for a celebration) without committing
    to a fully-authored descriptor. The base descriptor comes from the
    session's per-spec defaults.
    """

    spec_id: str
    node_name: str
    graph_id: str | None = None
    descriptor_overrides: dict = field(default_factory=dict)


# --- Stat effects ------------------------------------------------------------


@dataclass
class StatEffect:
    """A directive to change a character's stat.

    For Tier A, `stat` identifies the tuple; `delta` updates `StatTuple.value`.
    Tuple fields (awareness/focus/weight) are NEVER set by events directly —
    they drift slowly as a side effect over many outcomes (future phase).
    """

    role: str  # which cast slot receives the delta
    stat: StatName
    delta: float


@dataclass
class BranchOutcome:
    """Everything an event authored for a given branch.

    ``duration_minutes`` overrides the blueprint-level default when this
    branch is reached — the same player choice may resolve to outcomes
    of different lengths (e.g. "ate with friends" runs longer than
    "ate alone after the social check failed").
    """

    summary: str
    stat_effects: list[StatEffect] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)
    relationship_effects: list["RelationshipEffect"] = field(default_factory=list)
    duration_minutes: int | None = None


@dataclass
class RelationshipEffect:
    """Mutate a relationship between two cast slots."""

    source_role: str
    target_role: str
    familiarity: float = 0.0
    trust: float = 0.0
    tension: float = 0.0
    attraction: float = 0.0


# --- Blueprint ---------------------------------------------------------------


@dataclass
class EventBlueprint:
    id: str
    tags: set[str] = field(default_factory=set)
    participants: list[RoleSlot] = field(default_factory=list)
    blocks: list[SceneBlock] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    unlocks: list[str] = field(default_factory=list)
    disables: list[str] = field(default_factory=list)
    weight_modifiers: list[WeightRule] = field(default_factory=list)
    base_weight: float = 1.0
    outcomes: dict[str, BranchOutcome] = field(default_factory=dict)
    carries_arc_context: bool = False
    location: LocationCue | None = None
    duration_minutes: int = 60


@dataclass
class EventInstance:
    """A blueprint + a concrete cast, ready to run."""

    blueprint: EventBlueprint
    cast: dict[str, Character]  # role -> character


# --- Game state / context ---------------------------------------------------


@dataclass
class GameContext:
    """Lightweight, per-call view of current state — passed to weight rules
    and narration. Kept minimal so blueprint authors don't need to reason
    about the whole world."""

    week_phase: WeekPhase
    team_morale: float = 0.0
    momentum: float = 0.0
    location: str | None = None
    flags: set[str] = field(default_factory=set)


@dataclass
class GameState:
    """The mutable world state. `save.py` will serialise this in Phase 5."""

    characters: dict[str, Character] = field(default_factory=dict)
    outcome_log: list[OutcomeRecord] = field(default_factory=list)
    completed_event_ids: set[str] = field(default_factory=set)
    disabled_event_ids: set[str] = field(default_factory=set)
    week_phase: WeekPhase = field(default_factory=lambda: WeekPhase(1, 1))
    clocks: list = field(default_factory=list)  # populated in Phase 5
    # Hour-precision world clock — see ``engine.clock``. Initialised to
    # Monday 08:00 of the current week; mutated by ``advance_time``.
    clock: WorldClock = field(default_factory=_default_clock)


# --- Eligibility & casting --------------------------------------------------


def check_prerequisites(
    blueprint: EventBlueprint, state: GameState
) -> bool:
    """All prereqs have fired, and the event isn't disabled."""
    if blueprint.id in state.disabled_event_ids:
        return False
    return all(pid in state.completed_event_ids for pid in blueprint.prerequisites)


def can_cast(
    blueprint: EventBlueprint, state: GameState
) -> bool:
    """Enough eligible characters exist to fill every required role slot.

    Greedy first-fit; sufficient for Phase 3.
    """
    _, ok = _try_cast(blueprint, state, rng=None)
    return ok


def cast_event(
    blueprint: EventBlueprint,
    state: GameState,
    rng: _random.Random,
) -> dict[str, Character] | None:
    """Return a concrete cast mapping role -> character, or None if infeasible."""
    cast, ok = _try_cast(blueprint, state, rng=rng)
    return cast if ok else None


def _try_cast(
    blueprint: EventBlueprint,
    state: GameState,
    rng: _random.Random | None,
) -> tuple[dict[str, Character], bool]:
    """Greedy cast. Fails fast on the first required slot that has no eligible
    character. Optional slots may be left unfilled."""
    used: set[str] = set()
    cast: dict[str, Character] = {}
    all_chars = list(state.characters.values())

    for slot in blueprint.participants:
        pool = [c for c in all_chars if c.id not in used]
        if slot.filter is not None:
            pool = [c for c in pool if slot.filter(c)]
        if not pool:
            if slot.optional:
                continue
            return cast, False
        choice = rng.choice(pool) if rng is not None else pool[0]
        cast[slot.role] = choice
        used.add(choice.id)

    return cast, True


# --- Weighting & selection --------------------------------------------------


RECENCY_WINDOW = 6  # events back to consider
RECENCY_FLOOR = 0.2  # multiplier applied if the event fired just now
CLOCK_WEIGHT_SCALE = 2.5


def recency_penalty(event_id: str, outcome_log: Sequence[OutcomeRecord]) -> float:
    """Return a multiplier in [RECENCY_FLOOR, 1] that grows back toward 1
    as distance from the last occurrence increases."""
    for i, o in enumerate(reversed(outcome_log[-RECENCY_WINDOW:])):
        if o.event_id == event_id:
            # i=0 is most recent; distance-based recovery.
            ratio = i / RECENCY_WINDOW
            return RECENCY_FLOOR + (1.0 - RECENCY_FLOOR) * ratio
    return 1.0


def compute_weight(
    blueprint: EventBlueprint,
    context: GameContext,
    state: GameState,
) -> float:
    w = blueprint.base_weight
    w *= recency_penalty(blueprint.id, state.outcome_log)
    for rule in blueprint.weight_modifiers:
        w *= max(0.0, rule.predicate(context, state))
    # Clock contributions: each clock targeting this event adds current*scale.
    # Actual Clock class lands in Phase 5; duck-type for now.
    for clock in getattr(state, "clocks", []) or []:
        if getattr(clock, "target_event_id", None) == blueprint.id:
            w += getattr(clock, "current", 0.0) * CLOCK_WEIGHT_SCALE
    return max(w, 0.0)


def select_event(
    candidates: Sequence[EventBlueprint],
    context: GameContext,
    state: GameState,
    rng: _random.Random,
) -> EventBlueprint | None:
    """Choose an event from the candidate pool by weight, or return None if
    nothing is eligible."""
    eligible = [
        e
        for e in candidates
        if check_prerequisites(e, state) and can_cast(e, state)
    ]
    if not eligible:
        return None
    weights = [compute_weight(e, context, state) for e in eligible]
    if sum(weights) <= 0:
        return None
    return rng.choices(eligible, weights=weights, k=1)[0]


# --- Outcome resolution -----------------------------------------------------


def resolve_outcome(
    blueprint: EventBlueprint,
    branch: str,
    cast: Mapping[str, Character],
    state: GameState,
    prior_outcome: OutcomeRecord | None = None,
) -> OutcomeRecord:
    """Apply a branch's effects to `state` and return the OutcomeRecord.

    Mutates: character stats, relationships, and `state.outcome_log` /
    `completed_event_ids` / `disabled_event_ids`. Narrative summary is the
    branch's authored string (LLM enhancement is a Phase 4 concern).
    """
    if branch not in blueprint.outcomes:
        raise KeyError(
            f"blueprint {blueprint.id!r} has no outcome for branch {branch!r}"
        )
    outcome = blueprint.outcomes[branch]

    stat_deltas: dict[str, dict[str, float]] = {}
    for effect in outcome.stat_effects:
        char = cast.get(effect.role)
        if char is None:
            continue
        _apply_stat_delta(char, effect.stat, effect.delta)
        stat_deltas.setdefault(char.id, {})[effect.stat.value] = (
            stat_deltas.get(char.id, {}).get(effect.stat.value, 0.0)
            + effect.delta
        )

    for re in outcome.relationship_effects:
        src = cast.get(re.source_role)
        tgt = cast.get(re.target_role)
        if src is None or tgt is None:
            continue
        _apply_relationship_delta(src, tgt, re)

    arc_summary = None
    if blueprint.carries_arc_context:
        if prior_outcome and prior_outcome.arc_summary:
            arc_summary = f"{prior_outcome.arc_summary}. {outcome.summary}"
        else:
            arc_summary = outcome.summary

    record = OutcomeRecord(
        event_id=blueprint.id,
        timestamp=state.week_phase,
        participants={role: c.id for role, c in cast.items()},
        branch_taken=branch,
        summary=outcome.summary,
        arc_summary=arc_summary,
        stat_deltas=stat_deltas,
        flags=set(outcome.flags),
    )
    state.outcome_log.append(record)
    state.completed_event_ids.add(blueprint.id)
    for disable_id in blueprint.disables:
        state.disabled_event_ids.add(disable_id)

    # Tier A characters accumulate history.
    for char in cast.values():
        if isinstance(char, TierACharacter):
            char.event_history.append(record)

    return record


# --- Internal mutation helpers ----------------------------------------------


def _apply_stat_delta(
    char: Character, stat: StatName, delta: float
) -> None:
    """Move a character's stat by delta, clamped to [0, 1].

    For Tier A, mutates `StatTuple.value` only. Tuple awareness/focus/weight
    are NEVER touched by direct event effects — they drift via a slow-time
    mechanism introduced later.
    """
    from .stats import StatTuple, clamp

    current = char.stats.get(stat)
    if current is None:
        if isinstance(char, TierACharacter):
            char.stats[stat] = StatTuple(value=clamp(0.5 + delta))
        else:
            char.stats[stat] = clamp(0.5 + delta)
        return
    if isinstance(current, StatTuple):
        current.value = clamp(current.value + delta)
    else:
        char.stats[stat] = clamp(current + delta)


def _apply_relationship_delta(
    src: Character, tgt: Character, re: RelationshipEffect
) -> None:
    from .relationships import RelationshipState
    from .stats import clamp

    rel = src.relationships.get(tgt.id)
    if rel is None:
        rel = RelationshipState()
        src.relationships[tgt.id] = rel
    rel.familiarity = clamp(rel.familiarity + re.familiarity)
    rel.trust = clamp(rel.trust + re.trust)
    rel.tension = clamp(rel.tension + re.tension)
    rel.attraction = clamp(rel.attraction + re.attraction)
