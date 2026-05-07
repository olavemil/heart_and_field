"""Tests for engine.character_factory (Phase 18A)."""

import random
from statistics import fmean

import pytest

from engine.character_factory import (
    FIRST_NAMES_FEMININE,
    FIRST_NAMES_MASCULINE,
    LAST_NAMES,
    ROLE_STAT_PROFILES,
    _slug_id,
    generate_character,
    generate_name,
    random_descriptor,
    random_quirks,
    random_stats_flat,
    random_stats_tuple,
)
from engine.characters import CharacterRole, TierACharacter, TierBCharacter
from engine.quirks import Quirk, QuirkDomain, QuirkPattern
from engine.sprite_pool import (
    AgeBucket,
    Build,
    CharacterDescriptor,
    GenderPresentation,
    SkinTone,
)
from engine.stats import StatName, StatTuple


# --- Names -----------------------------------------------------------------


class TestGenerateName:
    def test_returns_first_and_last(self):
        first, last = generate_name(random.Random(0))
        assert first
        assert last
        assert last in LAST_NAMES

    def test_masculine_bias_uses_masc_pool(self):
        rng = random.Random(0)
        firsts = {
            generate_name(rng, gender_presentation=GenderPresentation.MASCULINE)[0]
            for _ in range(80)
        }
        # Should not include feminine-only entries.
        feminine_only = set(FIRST_NAMES_FEMININE) - set(FIRST_NAMES_MASCULINE)
        assert not (firsts & feminine_only)

    def test_feminine_bias_uses_fem_pool(self):
        rng = random.Random(1)
        firsts = {
            generate_name(rng, gender_presentation=GenderPresentation.FEMININE)[0]
            for _ in range(80)
        }
        masculine_only = set(FIRST_NAMES_MASCULINE) - set(FIRST_NAMES_FEMININE)
        assert not (firsts & masculine_only)

    def test_androgynous_draws_from_all_pools(self):
        rng = random.Random(2)
        firsts = {
            generate_name(rng, gender_presentation=GenderPresentation.ANDROGYNOUS)[0]
            for _ in range(200)
        }
        # Across enough draws we should see both pool flavours.
        assert firsts & set(FIRST_NAMES_MASCULINE)
        assert firsts & set(FIRST_NAMES_FEMININE)


# --- Stats -----------------------------------------------------------------


class TestRandomStats:
    def test_flat_returns_value_per_stat(self):
        stats = random_stats_flat(CharacterRole.STRIKER, random.Random(0))
        for stat in StatName:
            assert stat in stats
            assert 0.0 <= stats[stat] <= 1.0

    def test_tuple_returns_tuple_per_stat(self):
        stats = random_stats_tuple(CharacterRole.STRIKER, random.Random(0))
        for stat in StatName:
            t = stats[stat]
            assert isinstance(t, StatTuple)
            assert 0.0 <= t.value <= 1.0
            assert 0.0 <= t.awareness <= 1.0
            assert 0.0 <= t.focus <= 1.0

    def test_means_converge_to_role_profile(self):
        # 1000 strikers should have a mean SPEED meaningfully above 0.5
        # because the profile lifts SPEED by +0.15.
        rng = random.Random(0)
        speeds = [
            random_stats_flat(CharacterRole.STRIKER, rng)[StatName.SPEED]
            for _ in range(1000)
        ]
        mean_speed = fmean(speeds)
        target = ROLE_STAT_PROFILES[CharacterRole.STRIKER][StatName.SPEED]
        # Within 0.03 of profile mean over 1000 draws.
        assert abs(mean_speed - target) < 0.03

    def test_defender_strength_above_baseline(self):
        rng = random.Random(0)
        means = [
            random_stats_flat(CharacterRole.DEFENDER, rng)[StatName.STRENGTH]
            for _ in range(500)
        ]
        # Defender profile boosts STRENGTH by +0.15 → mean ≈ 0.65.
        assert fmean(means) > 0.6

    def test_unknown_role_falls_back_to_baseline(self):
        # OTHER role has the flat baseline profile.
        rng = random.Random(0)
        means = [
            random_stats_flat(CharacterRole.OTHER, rng)[StatName.SPEED]
            for _ in range(500)
        ]
        assert 0.45 < fmean(means) < 0.55


# --- Quirks ---------------------------------------------------------------


class TestRandomQuirks:
    def test_count_in_requested_range(self):
        rng = random.Random(0)
        for _ in range(20):
            qs = random_quirks(rng, count_range=(2, 3))
            assert 2 <= len(qs) <= 3

    def test_no_duplicate_pairs(self):
        rng = random.Random(0)
        qs = random_quirks(rng, count_range=(3, 3))
        keys = [(q.domain, q.pattern) for q in qs]
        assert len(keys) == len(set(keys))

    def test_role_bias_shifts_distribution(self):
        # Strikers should pull PERFORMATIVE pattern more often than
        # the unbiased baseline (1.6× weight).
        rng = random.Random(0)
        striker_patterns = []
        for _ in range(500):
            qs = random_quirks(rng, count_range=(1, 1), role=CharacterRole.STRIKER)
            striker_patterns.append(qs[0].pattern)
        baseline_patterns = []
        rng2 = random.Random(0)
        for _ in range(500):
            qs = random_quirks(rng2, count_range=(1, 1))
            baseline_patterns.append(qs[0].pattern)

        striker_perf = striker_patterns.count(QuirkPattern.PERFORMATIVE)
        baseline_perf = baseline_patterns.count(QuirkPattern.PERFORMATIVE)
        assert striker_perf > baseline_perf

    def test_returns_quirk_instances(self):
        qs = random_quirks(random.Random(0))
        for q in qs:
            assert isinstance(q, Quirk)
            assert isinstance(q.domain, QuirkDomain)
            assert isinstance(q.pattern, QuirkPattern)


# --- Visual descriptor ---------------------------------------------------


class TestRandomDescriptor:
    def test_returns_descriptor(self):
        d = random_descriptor(random.Random(0))
        assert isinstance(d, CharacterDescriptor)
        assert d.gender_presentation in GenderPresentation
        assert d.age_bucket in AgeBucket
        assert d.skin_tone in SkinTone
        assert d.build in Build
        assert isinstance(d.hair, str) and d.hair

    def test_overrides_pinned(self):
        d = random_descriptor(
            random.Random(0),
            gender_presentation=GenderPresentation.FEMININE,
            age_bucket=AgeBucket.VETERAN,
        )
        assert d.gender_presentation == GenderPresentation.FEMININE
        assert d.age_bucket == AgeBucket.VETERAN

    def test_axes_cover_full_range_over_many_draws(self):
        rng = random.Random(0)
        sampled_skin = {
            random_descriptor(rng).skin_tone for _ in range(60)
        }
        assert sampled_skin == set(SkinTone)


# --- Composition ---------------------------------------------------------


class TestGenerateCharacter:
    def test_default_returns_tier_b(self):
        c = generate_character(CharacterRole.STRIKER, random.Random(0))
        assert isinstance(c, TierBCharacter)
        assert isinstance(c.stats[StatName.SPEED], float)
        assert c.id
        assert " " in c.name

    def test_tier_a_returns_tier_a_with_tuple_stats(self):
        c = generate_character(CharacterRole.STRIKER, random.Random(0), tier="A")
        assert isinstance(c, TierACharacter)
        assert isinstance(c.stats[StatName.SPEED], StatTuple)

    def test_explicit_id_used(self):
        c = generate_character(
            CharacterRole.STRIKER, random.Random(0), character_id="player",
        )
        assert c.id == "player"

    def test_explicit_name_used(self):
        c = generate_character(
            CharacterRole.STRIKER, random.Random(0), name=("Casey", "Lin"),
        )
        assert c.name == "Casey Lin"

    def test_explicit_quirks_used(self):
        q = [Quirk(QuirkDomain.PERFORMANCE, QuirkPattern.SEEKING)]
        c = generate_character(
            CharacterRole.STRIKER, random.Random(0), quirks=q,
        )
        assert c.quirks == q

    def test_determinism_under_same_seed(self):
        a = generate_character(CharacterRole.MIDFIELDER, random.Random(7))
        b = generate_character(CharacterRole.MIDFIELDER, random.Random(7))
        assert a == b

    def test_different_seeds_differ(self):
        a = generate_character(CharacterRole.MIDFIELDER, random.Random(7))
        b = generate_character(CharacterRole.MIDFIELDER, random.Random(8))
        assert a != b

    def test_save_round_trip_tier_b(self):
        c = generate_character(CharacterRole.DEFENDER, random.Random(0))
        restored = TierBCharacter.from_dict(c.to_dict())
        assert restored == c

    def test_save_round_trip_tier_a(self):
        c = generate_character(
            CharacterRole.STRIKER, random.Random(0), tier="A",
        )
        restored = TierACharacter.from_dict(c.to_dict())
        assert restored == c


class TestSlugId:
    def test_slug_id_unique_for_different_rng_state(self):
        a = _slug_id("Alex", "Carter", random.Random(0))
        b = _slug_id("Alex", "Carter", random.Random(1))
        assert a != b

    def test_slug_id_format(self):
        sid = _slug_id("Alex", "Carter", random.Random(0))
        assert sid.startswith("alex_carter_")
        assert len(sid.rsplit("_", 1)[1]) == 3
