import random
from pathlib import Path

import pytest

from engine.characters import CharacterRole, TierACharacter, TierBCharacter
from engine.content_loader import load_blueprints_from_path
from engine.events import (
    BranchOutcome,
    EventBlueprint,
    GameContext,
    GameState,
    RelationshipEffect,
    RoleSlot,
    SceneBlock,
    StatEffect,
    WeightRule,
    can_cast,
    cast_event,
    check_prerequisites,
    compute_weight,
    recency_penalty,
    resolve_outcome,
    select_event,
)
from engine.outcomes import OutcomeRecord, WeekPhase
from engine.stats import StatName, StatTuple


# --- Fixtures ---------------------------------------------------------------


def _tuple(v: float) -> StatTuple:
    return StatTuple(value=v, awareness=0.5, focus=0.5)


def make_player(id_: str = "player") -> TierACharacter:
    return TierACharacter(
        id=id_,
        name=id_,
        role=CharacterRole.STRIKER,
        stats={s: _tuple(0.5) for s in StatName},
    )


def make_teammate(id_: str) -> TierBCharacter:
    return TierBCharacter(
        id=id_,
        name=id_,
        role=CharacterRole.MIDFIELDER,
        stats={s: 0.5 for s in StatName},
    )


def make_state(*chars) -> GameState:
    return GameState(characters={c.id: c for c in chars})


def make_ctx(**overrides) -> GameContext:
    base = dict(week_phase=WeekPhase(1, 1), team_morale=0.0, momentum=0.0)
    base.update(overrides)
    return GameContext(**base)


# --- Casting ----------------------------------------------------------------


def test_cast_fills_required_roles():
    bp = EventBlueprint(
        id="t.a",
        participants=[
            RoleSlot(role="hero"),
            RoleSlot(role="foil"),
        ],
        blocks=[SceneBlock(id="m")],
        outcomes={"x": BranchOutcome(summary="x")},
    )
    state = make_state(make_player(), make_teammate("t1"))
    cast = cast_event(bp, state, random.Random(0))
    assert cast is not None
    assert set(cast.keys()) == {"hero", "foil"}
    assert cast["hero"].id != cast["foil"].id


def test_cast_respects_filter():
    bp = EventBlueprint(
        id="t.a",
        participants=[
            RoleSlot(role="player", filter=lambda c: c.id == "player"),
            RoleSlot(role="other", filter=lambda c: c.id != "player"),
        ],
        blocks=[SceneBlock(id="m")],
        outcomes={"x": BranchOutcome(summary="x")},
    )
    state = make_state(make_player(), make_teammate("t1"))
    cast = cast_event(bp, state, random.Random(0))
    assert cast["player"].id == "player"
    assert cast["other"].id == "t1"


def test_cast_fails_when_no_eligible_character():
    bp = EventBlueprint(
        id="t.a",
        participants=[RoleSlot(role="coach", filter=lambda c: False)],
        blocks=[SceneBlock(id="m")],
        outcomes={"x": BranchOutcome(summary="x")},
    )
    state = make_state(make_player())
    assert cast_event(bp, state, random.Random(0)) is None
    assert not can_cast(bp, state)


def test_optional_slot_may_be_empty():
    bp = EventBlueprint(
        id="t.a",
        participants=[
            RoleSlot(role="player", filter=lambda c: c.id == "player"),
            RoleSlot(
                role="witness",
                filter=lambda c: c.id == "nonexistent",
                optional=True,
            ),
        ],
        blocks=[SceneBlock(id="m")],
        outcomes={"x": BranchOutcome(summary="x")},
    )
    state = make_state(make_player())
    cast = cast_event(bp, state, random.Random(0))
    assert cast is not None
    assert "witness" not in cast


# --- Prerequisites ----------------------------------------------------------


def test_prereq_blocks_until_satisfied():
    bp = EventBlueprint(
        id="b",
        prerequisites=["a"],
        outcomes={"x": BranchOutcome(summary="x")},
    )
    state = GameState()
    assert not check_prerequisites(bp, state)
    state.completed_event_ids.add("a")
    assert check_prerequisites(bp, state)


def test_disabled_event_never_eligible():
    bp = EventBlueprint(
        id="b",
        outcomes={"x": BranchOutcome(summary="x")},
    )
    state = GameState(disabled_event_ids={"b"})
    assert not check_prerequisites(bp, state)


# --- Weights ----------------------------------------------------------------


def test_recency_penalty_cuts_weight_after_recent_fire():
    log = [
        OutcomeRecord(
            event_id="e",
            timestamp=WeekPhase(1, 1),
            participants={},
            branch_taken="x",
            summary="",
        )
    ]
    # Just fired → low multiplier; blank log → full multiplier.
    assert recency_penalty("e", log) < 0.3
    assert recency_penalty("never_fired", log) == 1.0


def test_weight_rules_multiply():
    bp = EventBlueprint(
        id="e",
        base_weight=2.0,
        weight_modifiers=[
            WeightRule(predicate=lambda c, s: 0.5),
            WeightRule(predicate=lambda c, s: 3.0),
        ],
        outcomes={"x": BranchOutcome(summary="x")},
    )
    state = GameState()
    ctx = make_ctx()
    # 2.0 * 1.0 (recency) * 0.5 * 3.0
    assert compute_weight(bp, ctx, state) == pytest.approx(3.0)


def test_weight_clock_contribution():
    from dataclasses import dataclass

    @dataclass
    class FakeClock:
        target_event_id: str
        current: float

    bp = EventBlueprint(
        id="e",
        base_weight=1.0,
        outcomes={"x": BranchOutcome(summary="x")},
    )
    state = GameState(clocks=[FakeClock(target_event_id="e", current=0.8)])
    ctx = make_ctx()
    # 1.0 + 0.8 * 2.5 = 3.0
    assert compute_weight(bp, ctx, state) == pytest.approx(3.0)


def test_select_event_reproducible():
    bp_a = EventBlueprint(
        id="a",
        participants=[RoleSlot(role="p", filter=lambda c: c.id == "player")],
        base_weight=1.0,
        outcomes={"x": BranchOutcome(summary="x")},
    )
    bp_b = EventBlueprint(
        id="b",
        participants=[RoleSlot(role="p", filter=lambda c: c.id == "player")],
        base_weight=5.0,
        outcomes={"x": BranchOutcome(summary="x")},
    )
    state = make_state(make_player())
    ctx = make_ctx()
    picks_1 = [select_event([bp_a, bp_b], ctx, state, random.Random(7)).id for _ in range(5)]
    picks_2 = [select_event([bp_a, bp_b], ctx, state, random.Random(7)).id for _ in range(5)]
    assert picks_1 == picks_2


def test_select_event_returns_none_when_all_disabled():
    bp = EventBlueprint(
        id="a",
        outcomes={"x": BranchOutcome(summary="x")},
    )
    state = GameState(disabled_event_ids={"a"})
    assert select_event([bp], make_ctx(), state, random.Random(0)) is None


# --- Resolution -------------------------------------------------------------


def test_resolve_applies_stat_delta_to_tier_a_tuple_value_only():
    player = make_player()
    original_awareness = player.stats[StatName.CONFIDENCE].awareness
    bp = EventBlueprint(
        id="e",
        participants=[RoleSlot(role="p", filter=lambda c: c.id == "player")],
        outcomes={
            "good": BranchOutcome(
                summary="s",
                stat_effects=[StatEffect("p", StatName.CONFIDENCE, 0.1)],
            )
        },
    )
    state = make_state(player)
    cast = cast_event(bp, state, random.Random(0))
    record = resolve_outcome(bp, "good", cast, state)
    assert player.stats[StatName.CONFIDENCE].value == pytest.approx(0.6)
    # Tuple fields other than `value` are untouched.
    assert player.stats[StatName.CONFIDENCE].awareness == original_awareness
    assert record.stat_deltas["player"]["confidence"] == pytest.approx(0.1)


def test_resolve_applies_relationship_effect():
    player = make_player()
    teammate = make_teammate("t1")
    bp = EventBlueprint(
        id="e",
        participants=[
            RoleSlot(role="a", filter=lambda c: c.id == "player"),
            RoleSlot(role="b", filter=lambda c: c.id == "t1"),
        ],
        outcomes={
            "x": BranchOutcome(
                summary="s",
                relationship_effects=[
                    RelationshipEffect(
                        source_role="a",
                        target_role="b",
                        familiarity=0.2,
                        trust=0.1,
                    )
                ],
            )
        },
    )
    state = make_state(player, teammate)
    cast = cast_event(bp, state, random.Random(0))
    resolve_outcome(bp, "x", cast, state)
    rel = player.relationships["t1"]
    assert rel.familiarity == pytest.approx(0.2)
    assert rel.trust == pytest.approx(0.6)  # 0.5 default + 0.1


def test_resolve_records_outcome_and_marks_complete():
    player = make_player()
    bp = EventBlueprint(
        id="e",
        participants=[RoleSlot(role="p", filter=lambda c: c.id == "player")],
        outcomes={"x": BranchOutcome(summary="done", flags={"public"})},
    )
    state = make_state(player)
    cast = cast_event(bp, state, random.Random(0))
    record = resolve_outcome(bp, "x", cast, state)
    assert record in state.outcome_log
    assert "e" in state.completed_event_ids
    assert record.flags == {"public"}
    assert record in player.event_history


def test_disables_propagate():
    player = make_player()
    bp = EventBlueprint(
        id="e",
        participants=[RoleSlot(role="p", filter=lambda c: c.id == "player")],
        disables=["other"],
        outcomes={"x": BranchOutcome(summary="s")},
    )
    state = make_state(player)
    cast = cast_event(bp, state, random.Random(0))
    resolve_outcome(bp, "x", cast, state)
    assert "other" in state.disabled_event_ids


def test_arc_summary_chains_across_arc_events():
    player = make_player()
    teammate = make_teammate("t1")
    bp1 = EventBlueprint(
        id="a1",
        participants=[
            RoleSlot(role="player", filter=lambda c: c.id == "player"),
            RoleSlot(role="target", filter=lambda c: c.id == "t1"),
        ],
        carries_arc_context=True,
        outcomes={"x": BranchOutcome(summary="They argued.")},
    )
    bp2 = EventBlueprint(
        id="a2",
        participants=[
            RoleSlot(role="player", filter=lambda c: c.id == "player"),
            RoleSlot(role="target", filter=lambda c: c.id == "t1"),
        ],
        prerequisites=["a1"],
        carries_arc_context=True,
        outcomes={"x": BranchOutcome(summary="He apologised.")},
    )
    state = make_state(player, teammate)

    cast1 = cast_event(bp1, state, random.Random(0))
    o1 = resolve_outcome(bp1, "x", cast1, state)
    cast2 = cast_event(bp2, state, random.Random(0))
    o2 = resolve_outcome(bp2, "x", cast2, state, prior_outcome=o1)

    assert o1.arc_summary == "They argued."
    assert o2.arc_summary == "They argued.. He apologised."


def test_unknown_branch_raises():
    player = make_player()
    bp = EventBlueprint(
        id="e",
        participants=[RoleSlot(role="p", filter=lambda c: c.id == "player")],
        outcomes={"good": BranchOutcome(summary="s")},
    )
    state = make_state(player)
    cast = cast_event(bp, state, random.Random(0))
    with pytest.raises(KeyError):
        resolve_outcome(bp, "bogus", cast, state)


# --- Content loader ---------------------------------------------------------


def test_loader_finds_all_authored_blueprints():
    # Content root is game/content.
    content_root = Path(__file__).resolve().parents[1] / "game" / "content"
    blueprints = load_blueprints_from_path(content_root / "events")
    ids = {b.id for b in blueprints}
    # A sampling of IDs from the authored set.
    expected = {
        "training.drill_partner",
        "training.showing_off",
        "training.coaching_moment",
        "downtime.shared_meal",
        "downtime.travel_reading",
        "conflict.blame_assignment",
        "conflict.apology",
        "vuln.post_loss_confession",
        "vuln.injury_worry",
        "pregame.locker_room_speech",
        "pregame.ritual",
    }
    missing = expected - ids
    assert not missing, f"missing blueprints: {missing}"
    # No duplicates.
    assert len(ids) == len(blueprints)


def test_loaded_blueprints_are_executable():
    """Pick a simple one, cast, resolve — smoke test the authored content."""
    content_root = Path(__file__).resolve().parents[1] / "game" / "content"
    blueprints = {
        b.id: b for b in load_blueprints_from_path(content_root / "events")
    }
    bp = blueprints["downtime.travel_reading"]
    state = make_state(make_player())
    cast = cast_event(bp, state, random.Random(0))
    assert cast is not None
    record = resolve_outcome(bp, "reflective", cast, state)
    assert "reflection" in record.stat_deltas["player"]


# --- End-to-end selection ---------------------------------------------------


def test_full_week_selects_varied_events():
    """Load all content, run 20 selection cycles, ensure no crash and the
    outcome log grows."""
    content_root = Path(__file__).resolve().parents[1] / "game" / "content"
    blueprints = load_blueprints_from_path(content_root / "events")

    state = make_state(
        make_player(),
        make_teammate("mid1"),
        make_teammate("mid2"),
        TierBCharacter(
            id="coach",
            name="coach",
            role=CharacterRole.MANAGER,
            stats={s: 0.6 for s in StatName},
        ),
    )
    ctx = make_ctx()
    rng = random.Random(0)

    prior = None
    fires = 0
    for _ in range(20):
        bp = select_event(blueprints, ctx, state, rng)
        if bp is None:
            continue
        cast = cast_event(bp, state, rng)
        if cast is None:
            continue
        # Pick any branch.
        branch = next(iter(bp.outcomes))
        prior = resolve_outcome(bp, branch, cast, state, prior_outcome=prior)
        fires += 1

    assert fires >= 5
    assert len(state.outcome_log) == fires
