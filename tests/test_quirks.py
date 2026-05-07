"""Tests for the quirk system (engine.quirks)."""

import pytest

from engine.quirks import (
    QUIRK_AFFINITIES,
    QUIRK_EVENT_BIAS,
    QUIRK_FRICTIONS,
    QUIRK_STAT_MODIFIERS,
    Quirk,
    QuirkDomain,
    QuirkPattern,
    QuirkReveal,
    QuirkVisibility,
    cast_event_weight_multiplier,
    event_weight_multiplier,
    has_affinity,
    has_friction,
    pairwise_affinity,
    pairwise_friction,
    stat_modifier,
    total_stat_modifier,
    visible_to_observer,
)
from engine.stats import StatName


def Q(domain: QuirkDomain, pattern: QuirkPattern) -> Quirk:
    return Quirk(domain, pattern)


# --- Quirk dataclass -------------------------------------------------------


class TestQuirk:
    def test_equality_keys_on_pair(self):
        a = Q(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING)
        b = Q(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING)
        c = Q(QuirkDomain.PERFORMANCE, QuirkPattern.AVOIDANT)
        assert a == b
        assert a != c
        assert hash(a) == hash(b)

    def test_round_trip(self):
        q = Q(QuirkDomain.SOCIAL, QuirkPattern.SEEKING)
        assert Quirk.from_dict(q.to_dict()) == q


# --- Affinity / friction ---------------------------------------------------


class TestAffinityFriction:
    def test_affinity_undirected(self):
        a = Q(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING)
        b = Q(QuirkDomain.PERFORMANCE, QuirkPattern.COMPULSIVE)
        # Listed only one direction in the table; lookup must accept both.
        assert has_affinity(a, b)
        assert has_affinity(b, a)

    def test_unrelated_pair_has_no_affinity(self):
        a = Q(QuirkDomain.SOCIAL, QuirkPattern.AVOIDANT)
        b = Q(QuirkDomain.PHYSICAL, QuirkPattern.RIGID)
        assert not has_affinity(a, b)

    def test_friction_undirected(self):
        a = Q(QuirkDomain.COGNITIVE, QuirkPattern.RIGID)
        b = Q(QuirkDomain.SOCIAL, QuirkPattern.SEEKING)
        assert has_friction(a, b)
        assert has_friction(b, a)

    def test_pairwise_counts(self):
        a_quirks = [
            Q(QuirkDomain.COGNITIVE, QuirkPattern.RIGID),
            Q(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING),
        ]
        b_quirks = [
            Q(QuirkDomain.PERFORMANCE, QuirkPattern.COMPULSIVE),
        ]
        # COGNITIVE+RIGID ↔ PERFORMANCE+COMPULSIVE: affinity (yes)
        # PERFORMANCE+SEEKING ↔ PERFORMANCE+COMPULSIVE: affinity (yes)
        assert pairwise_affinity(a_quirks, b_quirks) == 2

    def test_friction_count(self):
        a_quirks = [Q(QuirkDomain.SOCIAL, QuirkPattern.AVOIDANT)]
        b_quirks = [Q(QuirkDomain.SOCIAL, QuirkPattern.SEEKING)]
        assert pairwise_friction(a_quirks, b_quirks) == 1


# --- Visibility ------------------------------------------------------------


class TestVisibility:
    def test_visible_always(self):
        q = Q(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING)
        reveal = QuirkReveal(quirk=q, visibility=QuirkVisibility.VISIBLE)
        assert visible_to_observer(reveal)
        assert visible_to_observer(reveal, observer_familiarity=0.0)

    def test_hidden_until_familiarity_threshold(self):
        q = Q(QuirkDomain.SOCIAL, QuirkPattern.AVOIDANT)
        reveal = QuirkReveal(
            quirk=q,
            visibility=QuirkVisibility.HIDDEN,
            reveal_familiarity=0.6,
        )
        assert not visible_to_observer(reveal, observer_familiarity=0.5)
        assert visible_to_observer(reveal, observer_familiarity=0.6)
        assert visible_to_observer(reveal, observer_familiarity=0.9)

    def test_hidden_until_event_tag(self):
        q = Q(QuirkDomain.EMOTIONAL, QuirkPattern.REACTIVE)
        reveal = QuirkReveal(
            quirk=q,
            visibility=QuirkVisibility.HIDDEN,
            reveal_event_tags=["vulnerability"],
        )
        assert not visible_to_observer(reveal, witnessed_event_tags=["training"])
        assert visible_to_observer(reveal, witnessed_event_tags=["vulnerability"])

    def test_inferable_treated_like_hidden_without_signal(self):
        q = Q(QuirkDomain.PERFORMANCE, QuirkPattern.AVOIDANT)
        reveal = QuirkReveal(quirk=q, visibility=QuirkVisibility.INFERABLE)
        assert not visible_to_observer(reveal)

    def test_round_trip(self):
        q = Q(QuirkDomain.COGNITIVE, QuirkPattern.RIGID)
        reveal = QuirkReveal(
            quirk=q,
            visibility=QuirkVisibility.HIDDEN,
            reveal_event_tags=["training"],
            reveal_familiarity=0.7,
        )
        assert QuirkReveal.from_dict(reveal.to_dict()).to_dict() == reveal.to_dict()


# --- Stat modifiers --------------------------------------------------------


class TestStatModifiers:
    def test_modifier_for_known_quirk(self):
        q = Q(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING)
        assert stat_modifier(q, StatName.STAMINA) == 0.05

    def test_unknown_quirk_returns_zero(self):
        q = Q(QuirkDomain.PHYSICAL, QuirkPattern.AVOIDANT)
        assert stat_modifier(q, StatName.STAMINA) == 0.0

    def test_unknown_stat_returns_zero(self):
        q = Q(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING)
        # No modifier for SPEED in the seeking row? Check actual table.
        # We check INSECURITY which the table doesn't list for that pair.
        assert stat_modifier(q, StatName.INSECURITY) == 0.0

    def test_stacks_additively(self):
        # Two PHYSICAL+SEEKING quirks both contribute.
        quirks = [
            Q(QuirkDomain.PHYSICAL, QuirkPattern.SEEKING),
            Q(QuirkDomain.PHYSICAL, QuirkPattern.SEEKING),
        ]
        single = stat_modifier(quirks[0], StatName.STAMINA)
        assert total_stat_modifier(quirks, StatName.STAMINA) == single * 2


# --- Event weight bias -----------------------------------------------------


class TestEventWeight:
    def test_no_quirks_returns_one(self):
        assert event_weight_multiplier([], ["training"]) == 1.0

    def test_no_matching_tag_returns_one(self):
        q = Q(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING)
        assert event_weight_multiplier([q], ["meditation"]) == 1.0

    def test_seeker_boosts_training(self):
        q = Q(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING)
        # Authored value: 1.5
        assert event_weight_multiplier([q], ["training"]) == 1.5

    def test_avoidant_penalises_social(self):
        q = Q(QuirkDomain.SOCIAL, QuirkPattern.AVOIDANT)
        m = event_weight_multiplier([q], ["social"])
        assert 0.0 < m < 1.0

    def test_multiple_quirks_compose(self):
        seeker = Q(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING)
        compulsive = Q(QuirkDomain.COGNITIVE, QuirkPattern.COMPULSIVE)
        # Both boost training: 1.5 * 1.3 = 1.95
        m = event_weight_multiplier([seeker, compulsive], ["training"])
        assert m == pytest.approx(1.5 * 1.3)


class TestCastWeightBias:
    def test_friction_pair_boosts_conflict_event(self):
        # Cast with friction pair (avoidant ↔ seeking).
        with_friction = [
            [Q(QuirkDomain.SOCIAL, QuirkPattern.AVOIDANT)],
            [Q(QuirkDomain.SOCIAL, QuirkPattern.SEEKING)],
        ]
        # Same per-character event biases, but no friction relation.
        # PERFORMANCE+SEEKING also has no conflict tag bias, isolating
        # the cast-level friction bump as the sole differentiator.
        without_friction = [
            [Q(QuirkDomain.SOCIAL, QuirkPattern.AVOIDANT)],
            [Q(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING)],
        ]
        m_with = cast_event_weight_multiplier(with_friction, ["conflict"])
        m_without = cast_event_weight_multiplier(without_friction, ["conflict"])
        assert m_with > m_without

    def test_affinity_pair_boosts_warm_event(self):
        cast = [
            [Q(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING)],
            [Q(QuirkDomain.PERFORMANCE, QuirkPattern.COMPULSIVE)],
        ]
        m_with = cast_event_weight_multiplier(cast, ["social"])
        m_without = cast_event_weight_multiplier(cast, ["training"])
        # Both characters' training bias kicks in for the "without"
        # case, so we compare against 1.0 instead.
        assert m_with > 1.0

    def test_empty_cast_safe(self):
        assert cast_event_weight_multiplier([], ["conflict"]) == 1.0


# --- Lookup-table integrity -----------------------------------------------


class TestTableIntegrity:
    def test_affinity_table_keys_and_values_are_valid_pairs(self):
        for key, values in QUIRK_AFFINITIES.items():
            assert isinstance(key[0], QuirkDomain)
            assert isinstance(key[1], QuirkPattern)
            for v in values:
                assert isinstance(v[0], QuirkDomain)
                assert isinstance(v[1], QuirkPattern)

    def test_friction_table_keys_and_values_are_valid_pairs(self):
        for key, values in QUIRK_FRICTIONS.items():
            assert isinstance(key[0], QuirkDomain)
            assert isinstance(key[1], QuirkPattern)
            for v in values:
                assert isinstance(v[0], QuirkDomain)
                assert isinstance(v[1], QuirkPattern)

    def test_stat_modifiers_use_valid_enum_keys(self):
        for key, mods in QUIRK_STAT_MODIFIERS.items():
            assert isinstance(key[0], QuirkDomain)
            assert isinstance(key[1], QuirkPattern)
            for stat, delta in mods.items():
                assert isinstance(stat, StatName)
                assert isinstance(delta, (int, float))

    def test_event_bias_multipliers_are_positive(self):
        for key, biases in QUIRK_EVENT_BIAS.items():
            for tag, mult in biases.items():
                assert mult > 0
                assert isinstance(tag, str)
