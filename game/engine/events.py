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
from .stats import StatName, StatTuple


def _default_clock() -> "WorldClock":
    """Factory used by ``GameState.clock`` — Monday 08:00 of week 1."""
    return WorldClock(week=1, weekday=Weekday.MON, hour=8, minute=0)


class PlayerStance(str, Enum):
    """How present and how agentive the player is in an event (Phase 24C).

    The player is always implicitly in the scene, but their *role* in it
    varies. Stance drives figure framing (how prominent the player
    silhouette is) and narration voice (acting vs reacting vs watching).

    - ``ACTOR`` — the player drives the scene (default; today's behaviour).
    - ``REACTOR`` — the scene happens to the player; they respond.
    - ``ONLOOKER`` — the player is part of the scene but on its edge.
    - ``SPECTATOR`` — the player mostly watches others; minimal agency.
    """

    ACTOR = "actor"
    REACTOR = "reactor"
    ONLOOKER = "onlooker"
    SPECTATOR = "spectator"


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
    scene_instance: str | None = None  # SceneInstance value, e.g. "bar_local"
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

    Multi-beat narration (Phase 24B). ``summary`` is the **result** beat
    (the consequence / where things land) and is always authored — it is
    the single-beat fallback. The two optional beats play *before* it,
    each on its own screen, so a resolved choice reads as action →
    reaction → result rather than one block:

    - ``action_summary`` — what the player did, immediately after the
      choice lands.
    - ``reaction_summary`` — the other party's reaction to it.

    Both use the same role-scoped pronoun slots as ``summary``
    (``{they:player}`` …) and are LLM-enhanced with journal continuity so
    each beat flows from the last. Leave them ``None`` to keep the event
    single-beat.
    """

    summary: str
    stat_effects: list[StatEffect] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)
    relationship_effects: list["RelationshipEffect"] = field(default_factory=list)
    duration_minutes: int | None = None
    action_summary: str | None = None
    reaction_summary: str | None = None
    # Tone the scene shifts to once this branch lands (Phase 24D). When
    # set, the figures re-frame for the reaction/result beats — a
    # sceptical coach turns angry, a tense room warms. ``None`` keeps the
    # event's opening tone throughout.
    result_tone: "EventTone | None" = None


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
    # Pre-choice premise beat (Phase 24B). Narrated after the atmospheric
    # scene intro and before the choice menu, on its own screen(s). Uses
    # role-scoped pronoun slots like the branch summaries. ``None`` keeps
    # the event's setup to the one-line scene intro only.
    setup: str | None = None
    # Authored stance *anchor* (Phase 24C). NOT the final stance — it is
    # the natural framing for this event type, which ``weighted_player_
    # stance`` biases toward but can deviate from based on player traits,
    # the prior event's stance (persistence), and chance. Defaults to
    # ACTOR so unannotated events lean foreground.
    player_stance: PlayerStance = PlayerStance.ACTOR

    # ---- Phase 17 — taxonomy + chaining + secret/quirk gating ---------
    #
    # All of these default to empty / None so existing blueprints keep
    # their behaviour. Authors layering on the addendum §4 model fill
    # them in incrementally.

    # Canonical addendum §4.3 event id, when applicable.
    event_id: "EventType | None" = None

    # Outgoing chain edges from this blueprint.
    chain_edges: list = field(default_factory=list)

    # Quirk bias hooks (addendum §2 + §4.6).
    boosted_by_quirks: list[tuple] = field(default_factory=list)
    penalised_by_quirks: list[tuple] = field(default_factory=list)

    # Secret gating (addendum §3.8 + §4.6).
    requires_aspects: list = field(default_factory=list)
    boosted_by_aspects: list = field(default_factory=list)
    requires_secret_role: "SecretRole | None" = None
    reveals_exposure: float = 0.0

    # Scene routing (addendum §4.6).
    valid_scene_types: list = field(default_factory=list)
    preferred_instances: list = field(default_factory=list)

    # Placeholder introduction — when set, firing this event resolves
    # the named placeholder ids into real characters at cast time.
    introduces_placeholders: list[str] = field(default_factory=list)


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
    # World-level secret registry — secrets can have memberships across
    # multiple characters, so they live here rather than on a single
    # character record. Phase 13 ships the structure; Phase 14 will
    # populate ``mechanical`` / ``description`` / ``aspect_phrases``.
    secrets: dict[str, "Secret"] = field(default_factory=dict)
    # Stable-id placeholders for characters secrets reference but the
    # world hasn't introduced yet. Phase 15 — see
    # ``engine.placeholders.resolve_placeholder``.
    placeholders: dict[str, "CharacterPlaceholder"] = field(default_factory=dict)
    # Where the player currently is on the scene graph: ``(graph_id,
    # node_name)`` or ``None`` before the first scene has been resolved.
    # Drives movement-cost accounting in ``resolve_scene``.
    current_location: tuple[str, str] | None = None
    # League season — fixtures, standings, opponent clubs. ``None`` for
    # legacy / test sessions that don't use the league system.
    season: "Season | None" = None


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
    *,
    pinned: Mapping[str, Character] | None = None,
) -> dict[str, Character] | None:
    """Return a concrete cast mapping role -> character, or None if infeasible.

    ``pinned`` forces specific characters into specific roles (e.g. the
    actual goal-scorer into the ``scorer`` role for an in-match event). A
    pinned character must still satisfy that slot's filter, or the cast
    fails.
    """
    cast, ok = _try_cast(blueprint, state, rng=rng, pinned=pinned)
    return cast if ok else None


def _try_cast(
    blueprint: EventBlueprint,
    state: GameState,
    rng: _random.Random | None,
    pinned: Mapping[str, Character] | None = None,
) -> tuple[dict[str, Character], bool]:
    """Greedy cast. Fails fast on the first required slot that has no eligible
    character. Optional slots may be left unfilled."""
    pinned = pinned or {}
    used: set[str] = set()
    cast: dict[str, Character] = {}
    all_chars = list(state.characters.values())

    for slot in blueprint.participants:
        if slot.role in pinned:
            who = pinned[slot.role]
            # A pinned character must still satisfy the slot filter.
            if slot.filter is not None and not slot.filter(who):
                if slot.optional:
                    continue
                return cast, False
            cast[slot.role] = who
            used.add(who.id)
            continue
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
CHAIN_BIAS_BOOST = 1.8  # multiplier for chain-edge continuations


def recency_penalty(event_id: str, outcome_log: Sequence[OutcomeRecord]) -> float:
    """Return a multiplier in [RECENCY_FLOOR, 1] that grows back toward 1
    as distance from the last occurrence increases."""
    for i, o in enumerate(reversed(outcome_log[-RECENCY_WINDOW:])):
        if o.event_id == event_id:
            # i=0 is most recent; distance-based recovery.
            ratio = i / RECENCY_WINDOW
            return RECENCY_FLOOR + (1.0 - RECENCY_FLOOR) * ratio
    return 1.0


def representative_cast(
    blueprint: EventBlueprint, state: GameState
) -> dict[str, Character]:
    """Pick a deterministic best-effort cast for weight computation.

    Used by ``select_event`` so quirk bias can read the *likely* cast's
    quirks before the actual RNG-driven cast happens. Picks the first
    eligible character per role (sorted by id) — does not consume RNG
    so selection stays reproducible. Optional roles with no candidate
    are skipped; required roles with no candidate also drop quietly
    (the slot just doesn't contribute to the quirk signal).
    """
    used: set[str] = set()
    cast: dict[str, Character] = {}
    chars_by_id = sorted(state.characters.values(), key=lambda c: c.id)
    for slot in blueprint.participants:
        for candidate in chars_by_id:
            if candidate.id in used:
                continue
            if slot.filter is not None and not slot.filter(candidate):
                continue
            cast[slot.role] = candidate
            used.add(candidate.id)
            break
    return cast


def _cast_quirks(cast: Mapping[str, Character]) -> list[list]:
    """Extract the per-character quirk lists from a cast for use by
    ``cast_event_weight_multiplier``. Defaults to empty for characters
    that pre-date the quirks field."""
    return [list(getattr(c, "quirks", [])) for c in cast.values()]


# ---------------------------------------------------------------------------
# Secret-driven gating (Phase 17 wiring)
# ---------------------------------------------------------------------------


def _cast_aspect_types(
    cast: Mapping[str, Character], state: GameState
) -> set:
    """Collect every ``AspectType`` carried by any secret one of the
    cast members is a member of. Used by ``boosted_by_aspects`` and
    ``requires_aspects`` checks.
    """
    cast_ids = {c.id for c in cast.values()}
    types: set = set()
    for secret in state.secrets.values():
        if not any(
            m.character_id in cast_ids for m in secret.memberships
        ):
            continue
        for aspect in secret.aspects:
            types.add(aspect.type)
    return types


def _cast_has_secret_role(
    cast: Mapping[str, Character], role, state: GameState
) -> bool:
    cast_ids = {c.id for c in cast.values()}
    for secret in state.secrets.values():
        for membership in secret.memberships:
            if membership.character_id in cast_ids and membership.role == role:
                return True
    return False


def meets_secret_requirements(
    blueprint: EventBlueprint,
    cast: Mapping[str, Character],
    state: GameState,
) -> bool:
    """Eligibility check for the addendum §3.8 / §4.6 secret gates.

    - ``requires_aspects``: at least one cast member must be a member
      of a secret carrying *each* listed aspect type. Empty list = no
      requirement.
    - ``requires_secret_role``: at least one cast member must hold a
      secret in this role.

    Returns ``True`` when no gates are set or all gates are satisfied.
    """
    requires_aspects = list(getattr(blueprint, "requires_aspects", []) or [])
    role = getattr(blueprint, "requires_secret_role", None)
    if not requires_aspects and role is None:
        return True
    cast_types = _cast_aspect_types(cast, state)
    for at in requires_aspects:
        if at not in cast_types:
            return False
    if role is not None and not _cast_has_secret_role(cast, role, state):
        return False
    return True


def _aspect_boost_multiplier(
    blueprint: EventBlueprint,
    cast: Mapping[str, Character],
    state: GameState,
    *,
    per_match_bump: float = 0.25,
) -> float:
    """Soft weight bump per matching ``boosted_by_aspects`` entry.

    A blueprint that authors `boosted_by_aspects=[AspectType.AGENDA,
    AspectType.HISTORY]` and has a cast where one member carries an
    AGENDA secret picks up a single bump (×1.25). Two matches stack
    (×1.5625) — multiplicative composition like the quirk bias.
    """
    boosters = list(getattr(blueprint, "boosted_by_aspects", []) or [])
    if not boosters:
        return 1.0
    cast_types = _cast_aspect_types(cast, state)
    matches = sum(1 for at in boosters if at in cast_types)
    return (1.0 + per_match_bump) ** matches


def _chain_bias(
    blueprint: EventBlueprint, state: GameState
) -> float:
    """Return a weight multiplier > 1 when the most recent outcome has
    a chain edge pointing at ``blueprint.event_id``.

    If the blueprint has no ``event_id``, or the most recent outcome has
    no ``taxonomy_id``, returns 1.0 (no bias). Only the *last* outcome
    is considered — chaining is a next-beat nudge, not an accumulation.
    """
    if blueprint.event_id is None:
        return 1.0
    if not state.outcome_log:
        return 1.0
    last = state.outcome_log[-1]
    last_tid = getattr(last, "taxonomy_id", None)
    if last_tid is None:
        return 1.0
    from .event_taxonomy import chains_from

    edges = chains_from(last_tid)
    for edge in edges:
        if edge.to_id == blueprint.event_id:
            return CHAIN_BIAS_BOOST
    return 1.0


def compute_weight(
    blueprint: EventBlueprint,
    context: GameContext,
    state: GameState,
    *,
    cast: Mapping[str, Character] | None = None,
) -> float:
    """Compute selection weight for ``blueprint`` under ``context`` /
    ``state``.

    When ``cast`` is provided, quirk-driven event-weight bias is applied:
    per-character tag multipliers + cast-level affinity/friction bumps.
    When ``cast`` is ``None``, the function is back-compat with pre-quirk
    callers — useful for tests that don't care about quirks.
    """
    w = blueprint.base_weight
    w *= recency_penalty(blueprint.id, state.outcome_log)
    for rule in blueprint.weight_modifiers:
        w *= max(0.0, rule.predicate(context, state))
    # Clock contributions: each clock targeting this event adds current*scale.
    # Actual Clock class lands in Phase 5; duck-type for now.
    for clock in getattr(state, "clocks", []) or []:
        if getattr(clock, "target_event_id", None) == blueprint.id:
            w += getattr(clock, "current", 0.0) * CLOCK_WEIGHT_SCALE
    if cast:
        # Local import to avoid a circular dependency at module load time
        # (quirks doesn't import events, but events being imported very
        # early in some tests means a top-level import could re-enter).
        from .quirks import cast_event_weight_multiplier

        w *= cast_event_weight_multiplier(_cast_quirks(cast), blueprint.tags)
        w *= _aspect_boost_multiplier(blueprint, cast, state)

    # Chain bias: boost this blueprint if the most recent outcome chains
    # into it via an EventChainEdge.
    w *= _chain_bias(blueprint, state)

    return max(w, 0.0)


def select_event(
    candidates: Sequence[EventBlueprint],
    context: GameContext,
    state: GameState,
    rng: _random.Random,
) -> EventBlueprint | None:
    """Choose an event from the candidate pool by weight, or return None
    if nothing is eligible.

    Uses a deterministic ``representative_cast`` per blueprint so quirk
    bias can shift selection based on who's likely to be cast. The
    actual RNG-driven cast happens later in ``cast_event``; this is a
    selection-time hint only.
    """
    eligible: list[EventBlueprint] = []
    for e in candidates:
        if not check_prerequisites(e, state):
            continue
        if not can_cast(e, state):
            continue
        # Secret-aware gating uses the representative cast; we'd run it
        # again below for weighting, but eligibility is the right time
        # to drop blueprints whose secret requirements can't be met.
        rep = representative_cast(e, state)
        if not meets_secret_requirements(e, rep, state):
            continue
        eligible.append(e)
    if not eligible:
        return None
    weights: list[float] = []
    for bp in eligible:
        rep_cast = representative_cast(bp, state)
        weights.append(compute_weight(bp, context, state, cast=rep_cast))
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
        taxonomy_id=blueprint.event_id,
        day_ordinal=state.clock.day_ordinal() if state.clock is not None else None,
    )
    state.outcome_log.append(record)
    state.completed_event_ids.add(blueprint.id)
    for disable_id in blueprint.disables:
        state.disabled_event_ids.add(disable_id)

    # Tier A characters accumulate history.
    for char in cast.values():
        if isinstance(char, TierACharacter):
            char.event_history.append(record)

    # Phase 17 wiring — secret exposure advance + placeholder introduction.
    _advance_secret_exposure(blueprint, cast, state)
    _introduce_placeholders(blueprint, state)

    return record


# --- Player stance resolution (Phase 24C) -----------------------------------
#
# The player's role in an event is not fixed by the blueprint. The authored
# ``player_stance`` is an *anchor*; the actual stance is sampled from
# weighted odds combining narrative cohesion (the anchor), the player's
# traits, continuity with the prior event's stance, and chance.

# Weighting knobs.
_STANCE_ANCHOR_BIAS = 1.0     # base weight for the authored anchor stance
_STANCE_FLOOR = 0.28          # base weight for the other stances
_STANCE_PERSISTENCE = 1.6     # boost for repeating the prior event's stance


def _stat_value(character: Character, stat: StatName, default: float = 0.5) -> float:
    """Read a stat as a scalar regardless of Tier (tuple value or flat)."""
    raw = getattr(character, "stats", {}).get(stat) if character is not None else None
    if isinstance(raw, StatTuple):
        return raw.value
    if isinstance(raw, (int, float)):
        return float(raw)
    return default


def _stance_trait_tilt(player: Character) -> dict["PlayerStance", float]:
    """Multiplicative tilt per stance from the player's traits.

    Assertive players (confidence, leadership) lean ACTOR; reflective
    players lean ONLOOKER; insecure players lean SPECTATOR; REACTOR is the
    neutral middle.
    """
    conf = _stat_value(player, StatName.CONFIDENCE)
    lead = _stat_value(player, StatName.LEADERSHIP)
    refl = _stat_value(player, StatName.REFLECTION)
    insec = _stat_value(player, StatName.INSECURITY, 0.0)
    return {
        PlayerStance.ACTOR: 0.6 + 0.8 * conf + 0.4 * lead,
        PlayerStance.REACTOR: 1.0,
        PlayerStance.ONLOOKER: 0.6 + 0.8 * refl,
        PlayerStance.SPECTATOR: 0.5 + 1.0 * insec,
    }


def weighted_player_stance(
    blueprint: EventBlueprint,
    player: Character | None,
    *,
    rng: "_random.Random",
    prior_stance: PlayerStance | None = None,
    has_others: bool = True,
) -> PlayerStance:
    """Sample the player's stance for one event instance.

    Biases toward the blueprint's authored anchor, tilts by the player's
    traits, and boosts continuity with ``prior_stance`` so roles are
    *relatively persistent* across consecutive events. SPECTATOR (watching
    others) is dropped when the player is the only person in the scene.
    Deterministic for a given ``rng`` state. With no player it falls back
    to the anchor.
    """
    anchor = blueprint.player_stance
    if player is None:
        return anchor

    candidates = list(PlayerStance)
    if not has_others:
        candidates = [s for s in candidates if s is not PlayerStance.SPECTATOR]
        if anchor is PlayerStance.SPECTATOR:
            anchor = PlayerStance.ONLOOKER  # can't spectate an empty room

    tilt = _stance_trait_tilt(player)
    weights: dict[PlayerStance, float] = {}
    for s in candidates:
        base = _STANCE_ANCHOR_BIAS if s is anchor else _STANCE_FLOOR
        w = base * tilt.get(s, 1.0)
        if prior_stance is not None and s is prior_stance:
            w *= _STANCE_PERSISTENCE
        weights[s] = w

    total = sum(weights.values())
    if total <= 0:
        return anchor
    roll = rng.random() * total
    acc = 0.0
    for s, w in weights.items():
        acc += w
        if roll <= acc:
            return s
    return candidates[-1]


def _advance_secret_exposure(
    blueprint: EventBlueprint,
    cast: Mapping[str, Character],
    state: GameState,
) -> None:
    """Apply ``blueprint.reveals_exposure`` to any cast-member secret
    whose ``reveal_triggers`` overlaps the blueprint's tags.

    The bump targets the secret's *global* exposure_level (what
    non-members perceive) — member exposure is governed by the
    membership's own exposure float and isn't touched here. Capped at
    1.0 so an event firing repeatedly doesn't push past KNOWN.
    """
    bump = float(getattr(blueprint, "reveals_exposure", 0.0) or 0.0)
    if bump <= 0:
        return
    cast_ids = {c.id for c in cast.values()}
    tags = set(blueprint.tags)
    for secret in state.secrets.values():
        if not (set(secret.reveal_triggers) & tags):
            continue
        if not any(m.character_id in cast_ids for m in secret.memberships):
            continue
        secret.exposure_level = min(1.0, secret.exposure_level + bump)


def _introduce_placeholders(
    blueprint: EventBlueprint, state: GameState
) -> None:
    """Resolve any placeholder ids the blueprint declares it
    introduces. Errors are swallowed so a content typo doesn't crash a
    play session (the unresolved placeholder simply stays around).
    """
    ids = list(getattr(blueprint, "introduces_placeholders", []) or [])
    if not ids:
        return
    # Local import to avoid a circular dep with the placeholders module.
    from .placeholders import resolve_placeholder

    for pid in ids:
        if pid not in state.placeholders:
            continue
        if pid in state.characters:
            continue
        try:
            resolve_placeholder(state, pid)
        except (KeyError, ValueError):
            # Placeholder vanished mid-resolution or id collided after
            # the pre-check; either way, skip and let dev tooling
            # surface it via ``placeholders.unresolved_references``.
            pass


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
