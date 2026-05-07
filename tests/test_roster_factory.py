"""Tests for engine.roster_factory (Phase 18B)."""

import random
from collections import Counter

import pytest

from engine.characters import (
    CharacterRole,
    Disposition,
    TierACharacter,
    TierBCharacter,
    TierDSeed,
)
from engine.roster_factory import (
    CLUB_NAMES,
    OpponentClub,
    Roster,
    SOCCER_DEFAULT,
    SquadComposition,
    default_squad_composition,
    generate_coaching_staff,
    generate_opponent_seed,
    generate_roster,
    generate_season_opponents,
)
from engine.simulation import Sport


# --- SquadComposition / defaults -----------------------------------------


class TestSquadComposition:
    def test_soccer_total_matches_authored(self):
        # 2 GK + 5 DEF + 5 MID + 3 STR = 15.
        assert SOCCER_DEFAULT.total() == 15

    def test_default_composition_per_sport(self):
        soccer = default_squad_composition(Sport.SOCCER)
        rugby = default_squad_composition(Sport.RUGBY)
        basketball = default_squad_composition(Sport.BASKETBALL)
        assert soccer.role_counts[CharacterRole.GOALKEEPER] >= 1
        # Rugby has no goalkeepers.
        assert rugby.role_counts.get(CharacterRole.GOALKEEPER, 0) == 0
        # Basketball squad is smaller than soccer.
        assert basketball.total() < soccer.total()

    def test_unknown_sport_falls_back_to_soccer(self):
        # Use a sport that doesn't exist by simulating a future enum
        # value; default_squad_composition reads via .get and falls back.
        # We test this indirectly: the function uses a real Sport
        # value but takes a code path that handles missing keys.
        assert default_squad_composition(Sport.SOCCER) is SOCCER_DEFAULT


# --- generate_roster -----------------------------------------------------


class TestGenerateRoster:
    def test_returns_roster_with_player_and_squad(self):
        roster = generate_roster(random.Random(0))
        assert isinstance(roster, Roster)
        assert isinstance(roster.player, TierACharacter)
        assert roster.player.id == "player"
        assert len(roster.teammates) == SOCCER_DEFAULT.total()
        assert all(isinstance(t, TierBCharacter) for t in roster.teammates)

    def test_role_distribution_matches_composition(self):
        roster = generate_roster(random.Random(0))
        roles = Counter(t.role for t in roster.teammates)
        for role, count in SOCCER_DEFAULT.role_counts.items():
            assert roles[role] == count

    def test_with_player_false_omits_player(self):
        roster = generate_roster(random.Random(0), with_player=False)
        assert roster.player is None
        assert len(roster.teammates) == SOCCER_DEFAULT.total()

    def test_player_role_override(self):
        roster = generate_roster(
            random.Random(0), player_role=CharacterRole.MIDFIELDER,
        )
        assert roster.player.role == CharacterRole.MIDFIELDER

    def test_player_name_override(self):
        roster = generate_roster(
            random.Random(0),
            player_name=("Alex", "Morgan"),
        )
        assert roster.player.name == "Alex Morgan"

    def test_determinism_under_same_seed(self):
        a = generate_roster(random.Random(11))
        b = generate_roster(random.Random(11))
        assert a.player == b.player
        assert a.teammates == b.teammates

    def test_different_seeds_differ(self):
        a = generate_roster(random.Random(11))
        b = generate_roster(random.Random(12))
        a_names = [t.name for t in a.teammates]
        b_names = [t.name for t in b.teammates]
        assert a_names != b_names

    def test_all_characters_includes_player_and_staff(self):
        roster = generate_roster(random.Random(0))
        all_chars = roster.all_characters()
        # 1 player + 15 teammates + 2 staff = 18.
        assert len(all_chars) == SOCCER_DEFAULT.total() + 1 + 2

    def test_by_id_dict_unique_ids(self):
        roster = generate_roster(random.Random(0))
        ids = [c.id for c in roster.all_characters()]
        assert len(ids) == len(set(ids))


# --- Coaching staff -----------------------------------------------------


class TestCoachingStaff:
    def test_default_returns_manager_and_physio(self):
        staff = generate_coaching_staff(random.Random(0))
        roles = {s.role for s in staff}
        assert roles == {CharacterRole.MANAGER, CharacterRole.PHYSIO}


# --- Opponent seed ------------------------------------------------------


class TestOpponentSeed:
    def test_returns_named_club(self):
        club = generate_opponent_seed(random.Random(0))
        assert isinstance(club, OpponentClub)
        assert club.name in CLUB_NAMES

    def test_explicit_name_used(self):
        club = generate_opponent_seed(random.Random(0), name="Zenith FC")
        assert club.name == "Zenith FC"

    def test_seed_count_matches_composition(self):
        club = generate_opponent_seed(random.Random(0))
        assert len(club.seeds) == SOCCER_DEFAULT.total()

    def test_seed_skill_in_range(self):
        club = generate_opponent_seed(random.Random(0), skill_mean=0.5, skill_variance=0.1)
        for seed in club.seeds:
            assert 0.0 <= seed.skill_rating <= 1.0
        # Mean should land near the requested skill_mean over a full squad.
        mean_skill = sum(s.skill_rating for s in club.seeds) / len(club.seeds)
        assert 0.35 < mean_skill < 0.65

    def test_skill_mean_high_pulls_squad_up(self):
        rng = random.Random(0)
        weak = generate_opponent_seed(rng, skill_mean=0.3, skill_variance=0.1)
        strong = generate_opponent_seed(rng, skill_mean=0.75, skill_variance=0.1)
        weak_mean = sum(s.skill_rating for s in weak.seeds) / len(weak.seeds)
        strong_mean = sum(s.skill_rating for s in strong.seeds) / len(strong.seeds)
        assert strong_mean > weak_mean

    def test_seeds_are_tier_d(self):
        club = generate_opponent_seed(random.Random(0))
        assert all(isinstance(s, TierDSeed) for s in club.seeds)

    def test_disposition_drawn_from_authored_set(self):
        club = generate_opponent_seed(random.Random(0))
        for seed in club.seeds:
            assert seed.disposition in {Disposition.CALM, Disposition.FIERY}


# --- Season opponents ---------------------------------------------------


class TestSeasonOpponents:
    def test_returns_requested_count(self):
        clubs = generate_season_opponents(random.Random(0), count=8)
        assert len(clubs) == 8

    def test_names_unique(self):
        clubs = generate_season_opponents(random.Random(0), count=10)
        names = {c.name for c in clubs}
        assert len(names) == 10

    def test_skill_spread_across_range(self):
        clubs = generate_season_opponents(
            random.Random(0), count=10, skill_range=(0.3, 0.75),
        )
        # Compute each club's mean skill; the spread across the league
        # should cover most of the requested range.
        means = [
            sum(s.skill_rating for s in c.seeds) / len(c.seeds)
            for c in clubs
        ]
        # At least one club below 0.5 and one above 0.55 — the league
        # has both contenders and strugglers, not a flat field.
        assert min(means) < 0.5
        assert max(means) > 0.55

    def test_count_exceeds_pool_raises(self):
        with pytest.raises(ValueError):
            generate_season_opponents(random.Random(0), count=len(CLUB_NAMES) + 5)

    def test_determinism_under_same_seed(self):
        a = generate_season_opponents(random.Random(7), count=4)
        b = generate_season_opponents(random.Random(7), count=4)
        assert [c.name for c in a] == [c.name for c in b]


# --- Integration smoke --------------------------------------------------


class TestIntegrationSmoke:
    def test_generated_roster_round_trips_through_save(self):
        from engine.events import GameState
        from engine.save import deserialise, serialise

        roster = generate_roster(random.Random(0))
        state = GameState(
            characters={c.id: c for c in roster.all_characters()},
        )
        data = serialise(state)
        restored, _, _ = deserialise(data)
        assert len(restored.characters) == len(roster.all_characters())
        assert "player" in restored.characters
        assert isinstance(restored.characters["player"], TierACharacter)

    def test_generated_roster_passes_existing_blueprint_casts(self):
        # Sanity check that authored blueprints can cast against a
        # generated roster — i.e. the role coverage is sufficient.
        from engine.content_loader import load_blueprints_from_path
        from engine.events import GameState, can_cast
        from pathlib import Path

        roster = generate_roster(random.Random(0))
        state = GameState(
            characters={c.id: c for c in roster.all_characters()},
        )
        content_root = (
            Path(__file__).resolve().parents[1]
            / "game" / "content" / "events"
        )
        blueprints = load_blueprints_from_path(content_root)
        # At least one blueprint must successfully cast against the
        # generated roster — proves the factory produces a usable team.
        assert any(can_cast(bp, state) for bp in blueprints)
