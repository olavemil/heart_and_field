import random
import statistics

import pytest

from engine.characters import (
    CharacterRole,
    Disposition,
    TierACharacter,
    TierBCharacter,
    TierDSeed,
    character_stat,
)
from engine.motivators import Motivator, MotivatorSource
from engine.outcomes import OutcomeRecord, WeekPhase
from engine.relationships import RelationshipDynamic, RelationshipState
from engine.stats import ObservableName, StatName, StatTuple


# --- Tier D projection -------------------------------------------------------


def test_tier_d_projection_respects_role_weighting():
    """Strikers project higher SPEED than defenders at the same skill rating."""
    striker = TierDSeed(role=CharacterRole.STRIKER, skill_rating=0.8)
    defender = TierDSeed(role=CharacterRole.DEFENDER, skill_rating=0.8)
    rng = random.Random(0)
    striker_speed = statistics.fmean(
        striker.project(StatName.SPEED, random.Random(i)) for i in range(200)
    )
    defender_speed = statistics.fmean(
        defender.project(StatName.SPEED, random.Random(i)) for i in range(200)
    )
    assert striker_speed > defender_speed


def test_tier_d_disposition_shifts_personality_stats():
    """Fiery disposition raises aggressiveness relative to calm."""
    fiery = TierDSeed(
        role=CharacterRole.MIDFIELDER,
        skill_rating=0.5,
        disposition=Disposition.FIERY,
    )
    calm = TierDSeed(
        role=CharacterRole.MIDFIELDER,
        skill_rating=0.5,
        disposition=Disposition.CALM,
    )
    fiery_agg = statistics.fmean(
        fiery.project(StatName.AGGRESSIVENESS, random.Random(i))
        for i in range(200)
    )
    calm_agg = statistics.fmean(
        calm.project(StatName.AGGRESSIVENESS, random.Random(i))
        for i in range(200)
    )
    assert fiery_agg > calm_agg + 0.1


def test_tier_d_form_trend_affects_confidence_only():
    hot = TierDSeed(
        role=CharacterRole.STRIKER, skill_rating=0.5, form_trend=1.0
    )
    cold = TierDSeed(
        role=CharacterRole.STRIKER, skill_rating=0.5, form_trend=-1.0
    )
    hot_conf = statistics.fmean(
        hot.project(StatName.CONFIDENCE, random.Random(i)) for i in range(200)
    )
    cold_conf = statistics.fmean(
        cold.project(StatName.CONFIDENCE, random.Random(i)) for i in range(200)
    )
    assert hot_conf > cold_conf

    # Strength shouldn't care about form.
    hot_str = statistics.fmean(
        hot.project(StatName.STRENGTH, random.Random(i)) for i in range(200)
    )
    cold_str = statistics.fmean(
        cold.project(StatName.STRENGTH, random.Random(i)) for i in range(200)
    )
    assert abs(hot_str - cold_str) < 0.05


def test_tier_d_projections_clamped():
    seed = TierDSeed(
        role=CharacterRole.STRIKER,
        skill_rating=1.0,
        form_trend=1.0,
        disposition=Disposition.FIERY,
    )
    for i in range(200):
        for stat in StatName:
            v = seed.project(stat, random.Random(i))
            assert 0.0 <= v <= 1.0


def test_tier_d_roundtrip():
    seed = TierDSeed(
        role=CharacterRole.GOALKEEPER,
        skill_rating=0.72,
        form_trend=-0.3,
        disposition=Disposition.GUARDED,
    )
    assert TierDSeed.from_dict(seed.to_dict()) == seed


# --- Tier A insecurity & observables ----------------------------------------


def _full_tuple_set(
    value: float = 0.5, awareness: float = 0.5, focus: float = 0.5
) -> dict[StatName, StatTuple]:
    return {
        s: StatTuple(value=value, awareness=awareness, focus=focus)
        for s in StatName
    }


def test_insecurity_emerges_from_tuple_distribution():
    """High focus + low awareness → high insecurity, without storing it."""
    c = TierACharacter(
        id="p1",
        name="Player",
        role=CharacterRole.STRIKER,
        stats=_full_tuple_set(value=0.5, awareness=0.1, focus=0.9),
    )
    assert c.insecurity() == pytest.approx(0.81)


def test_insecurity_low_when_aware_and_unfocused():
    c = TierACharacter(
        id="p1",
        name="Player",
        role=CharacterRole.STRIKER,
        stats=_full_tuple_set(value=0.5, awareness=0.9, focus=0.2),
    )
    assert c.insecurity() < 0.05


def test_tier_a_observable_computes_from_tuple_values():
    stats = _full_tuple_set(value=0.5)
    stats[StatName.CONFIDENCE] = StatTuple(value=1.0, awareness=0.5, focus=0.5)
    stats[StatName.INTROSPECTION] = StatTuple(
        value=0.0, awareness=0.5, focus=0.5
    )
    stats[StatName.INSECURITY] = StatTuple(
        value=0.0, awareness=0.5, focus=0.5
    )
    c = TierACharacter(
        id="p1",
        name="Player",
        role=CharacterRole.STRIKER,
        stats=stats,
    )
    assert c.observable(ObservableName.ARROGANCE) == pytest.approx(1.0)


def test_character_stat_unwraps_tier_a_and_b():
    a = TierACharacter(
        id="a",
        name="A",
        role=CharacterRole.STRIKER,
        stats={StatName.SPEED: StatTuple(value=0.7, awareness=0.5, focus=0.5)},
    )
    b = TierBCharacter(
        id="b",
        name="B",
        role=CharacterRole.DEFENDER,
        stats={StatName.SPEED: 0.4},
    )
    assert character_stat(a, StatName.SPEED) == pytest.approx(0.7)
    assert character_stat(b, StatName.SPEED) == pytest.approx(0.4)


# --- Round-trip serialisation -----------------------------------------------


def test_tier_a_roundtrip_preserves_everything():
    outcome = OutcomeRecord(
        event_id="evt1",
        timestamp=WeekPhase(season=1, week=3, phase=-1),
        participants={"hero": "p1", "rival": "p2"},
        branch_taken="confront",
        summary="They argued in the locker room.",
        arc_summary="A grudge took shape.",
        stat_deltas={"p1": {"confidence": -0.1}},
        flags={"public", "unresolved"},
    )
    c = TierACharacter(
        id="p1",
        name="Alex",
        nickname="Al",
        role=CharacterRole.STRIKER,
        stats={
            StatName.CONFIDENCE: StatTuple(
                value=0.6, awareness=0.4, focus=0.7, weight=-0.2
            ),
            StatName.STAMINA: StatTuple(value=0.8, awareness=0.9, focus=0.3),
        },
        motivators=[
            Motivator(
                target_stat=StatName.CONFIDENCE,
                delta=0.15,
                decay_rate=0.1,
                source=MotivatorSource.CROWD,
                salience=2.0,
            )
        ],
        relationships={
            "p2": RelationshipState(
                familiarity=0.6,
                trust=0.2,
                tension=0.8,
                dynamic=RelationshipDynamic.RIVAL,
                hidden_flags={"jealousy"},
            )
        },
        event_history=[outcome],
    )
    restored = TierACharacter.from_dict(c.to_dict())
    assert restored == c


def test_tier_b_roundtrip():
    b = TierBCharacter(
        id="b1",
        name="Coach",
        role=CharacterRole.MANAGER,
        stats={StatName.LEADERSHIP: 0.9, StatName.REFLECTION: 0.7},
        relationships={
            "p1": RelationshipState(
                familiarity=0.4,
                dynamic=RelationshipDynamic.MENTOR,
            )
        },
    )
    assert TierBCharacter.from_dict(b.to_dict()) == b
