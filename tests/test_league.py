"""Tests for engine.league — Phase 20 (league and progression)."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

# Ensure the game/ directory is on sys.path so that content modules
# (which use ``from engine.X``) resolve to the same classes as our
# imports below.  This mirrors the Ren'Py runtime path and avoids
# dual-module-path type mismatches in integration tests.
_game_dir = str(Path(__file__).resolve().parent.parent / "game")
if _game_dir not in sys.path:
    sys.path.insert(0, _game_dir)

from engine.characters import CharacterRole, Disposition, TierDSeed
from engine.league import (
    Fixture,
    LeagueConfig,
    LeagueFormat,
    LeagueStanding,
    LeagueTier,
    Season,
    TIER_SKILL_RANGES,
    _club_mean_skill,
    _opponent_club_from_dict,
    _opponent_club_to_dict,
    _poisson_draw,
    generate_fixtures,
    generate_season,
)
from engine.roster_factory import OpponentClub, generate_season_opponents


# ---------------------------------------------------------------------------
# LeagueConfig
# ---------------------------------------------------------------------------


class TestLeagueConfig:
    def test_defaults(self):
        lc = LeagueConfig()
        assert lc.club_name == "Ashworth Town"
        assert lc.opponent_count == 11
        assert lc.league_format == LeagueFormat.OPEN
        assert lc.tier == LeagueTier.SEMI_PRO

    def test_total_clubs(self):
        lc = LeagueConfig(opponent_count=9)
        assert lc.total_clubs == 10

    def test_season_weeks(self):
        lc = LeagueConfig(opponent_count=11)
        assert lc.season_weeks == 22

    def test_round_trip(self):
        lc = LeagueConfig(
            club_name="FC Test",
            opponent_count=7,
            league_format=LeagueFormat.CLOSED,
            tier=LeagueTier.PROFESSIONAL,
        )
        restored = LeagueConfig.from_dict(lc.to_dict())
        assert restored == lc

    def test_all_tiers_have_skill_ranges(self):
        for tier in LeagueTier:
            assert tier in TIER_SKILL_RANGES
            low, high = TIER_SKILL_RANGES[tier]
            assert 0.0 <= low < high <= 1.0

    def test_professional_harder_than_amateur(self):
        pro_low, pro_high = TIER_SKILL_RANGES[LeagueTier.PROFESSIONAL]
        am_low, am_high = TIER_SKILL_RANGES[LeagueTier.AMATEUR]
        assert pro_low > am_low
        assert pro_high > am_high


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


class TestFixture:
    def test_result_for_home_win(self):
        f = Fixture(week=1, home="A", away="B", home_goals=3, away_goals=1, played=True)
        assert f.result_for("A") == "W"
        assert f.result_for("B") == "L"

    def test_result_for_draw(self):
        f = Fixture(week=1, home="A", away="B", home_goals=1, away_goals=1, played=True)
        assert f.result_for("A") == "D"
        assert f.result_for("B") == "D"

    def test_result_for_unplayed(self):
        f = Fixture(week=1, home="A", away="B")
        assert f.result_for("A") is None

    def test_result_for_uninvolved(self):
        f = Fixture(week=1, home="A", away="B", home_goals=2, away_goals=0, played=True)
        assert f.result_for("C") is None

    def test_goals_for_and_against(self):
        f = Fixture(week=1, home="A", away="B", home_goals=3, away_goals=1, played=True)
        assert f.goals_for("A") == 3
        assert f.goals_against("A") == 1
        assert f.goals_for("B") == 1
        assert f.goals_against("B") == 3

    def test_opponent_of(self):
        f = Fixture(week=1, home="A", away="B")
        assert f.opponent_of("A") == "B"
        assert f.opponent_of("B") == "A"
        assert f.opponent_of("C") is None

    def test_round_trip(self):
        f = Fixture(week=3, home="X", away="Y", home_goals=2, away_goals=2, played=True)
        restored = Fixture.from_dict(f.to_dict())
        assert restored.week == f.week
        assert restored.home == f.home
        assert restored.away == f.away
        assert restored.home_goals == f.home_goals
        assert restored.away_goals == f.away_goals
        assert restored.played == f.played


# ---------------------------------------------------------------------------
# LeagueStanding
# ---------------------------------------------------------------------------


class TestLeagueStanding:
    def test_points_calculation(self):
        s = LeagueStanding(club="A", won=5, drawn=3, lost=2)
        assert s.points == 18  # 5*3 + 3

    def test_goal_difference(self):
        s = LeagueStanding(club="A", goals_for=15, goals_against=10)
        assert s.goal_difference == 5

    def test_sort_key_order(self):
        better = LeagueStanding(club="A", won=5, drawn=1, goals_for=20, goals_against=5)
        worse = LeagueStanding(club="B", won=4, drawn=4, goals_for=15, goals_against=10)
        assert better.sort_key > worse.sort_key

    def test_round_trip(self):
        s = LeagueStanding(club="A", played=10, won=5, drawn=3, lost=2, goals_for=15, goals_against=10)
        restored = LeagueStanding.from_dict(s.to_dict())
        assert restored.club == s.club
        assert restored.points == s.points
        assert restored.goal_difference == s.goal_difference


# ---------------------------------------------------------------------------
# Fixture generation
# ---------------------------------------------------------------------------


class TestFixtureGeneration:
    def test_even_team_count(self):
        clubs = ["A", "B", "C", "D"]
        fixtures = generate_fixtures(clubs, random.Random(0))
        # 4 teams → 6 rounds (3 per half × 2 halves), 2 matches per round = 12 fixtures.
        assert len(fixtures) == 12

    def test_odd_team_count(self):
        clubs = ["A", "B", "C"]
        fixtures = generate_fixtures(clubs, random.Random(0))
        # 3 teams → each plays 2 opponents × 2 legs = 4 games each.
        # Total fixtures = 3*4/2 = 6.
        assert len(fixtures) == 6

    def test_every_pair_meets_twice(self):
        clubs = ["A", "B", "C", "D"]
        fixtures = generate_fixtures(clubs, random.Random(0))
        pairs: dict[tuple[str, str], int] = {}
        for f in fixtures:
            key = (f.home, f.away)
            pairs[key] = pairs.get(key, 0) + 1
        # Every ordered pair (home, away) appears exactly once.
        for a in clubs:
            for b in clubs:
                if a == b:
                    continue
                assert pairs.get((a, b), 0) == 1, f"Missing {a} vs {b}"

    def test_12_teams_fixture_count(self):
        clubs = [f"Club_{i}" for i in range(12)]
        fixtures = generate_fixtures(clubs, random.Random(42))
        # 12 teams: 11 rounds per half × 2 halves = 22 rounds, 6 matches each = 132.
        assert len(fixtures) == 132

    def test_single_team_no_fixtures(self):
        assert generate_fixtures(["A"], random.Random(0)) == []

    def test_determinism(self):
        clubs = ["A", "B", "C", "D", "E", "F"]
        f1 = generate_fixtures(clubs, random.Random(42))
        f2 = generate_fixtures(clubs, random.Random(42))
        assert len(f1) == len(f2)
        for a, b in zip(f1, f2):
            assert a.home == b.home and a.away == b.away and a.week == b.week

    def test_different_seeds_different_order(self):
        clubs = ["A", "B", "C", "D", "E", "F"]
        f1 = generate_fixtures(clubs, random.Random(1))
        f2 = generate_fixtures(clubs, random.Random(2))
        # Same set of matchups, but round order differs.
        assert len(f1) == len(f2)
        weeks1 = [(f.week, f.home, f.away) for f in f1]
        weeks2 = [(f.week, f.home, f.away) for f in f2]
        assert weeks1 != weeks2


# ---------------------------------------------------------------------------
# OpponentClub serialisation
# ---------------------------------------------------------------------------


class TestOpponentClubSerialisation:
    def test_round_trip(self):
        club = OpponentClub(
            name="Test FC",
            seeds=[
                TierDSeed(role=CharacterRole.STRIKER, skill_rating=0.6),
                TierDSeed(role=CharacterRole.DEFENDER, skill_rating=0.4,
                          disposition=Disposition.FIERY),
            ],
        )
        d = _opponent_club_to_dict(club)
        restored = _opponent_club_from_dict(d)
        assert restored.name == club.name
        assert len(restored.seeds) == len(club.seeds)
        assert restored.seeds[0].skill_rating == club.seeds[0].skill_rating
        assert restored.seeds[1].disposition == club.seeds[1].disposition

    def test_empty_seeds(self):
        club = OpponentClub(name="Empty FC", seeds=[])
        d = _opponent_club_to_dict(club)
        restored = _opponent_club_from_dict(d)
        assert restored.seeds == []


# ---------------------------------------------------------------------------
# Season
# ---------------------------------------------------------------------------


def _make_season(seed: int = 42, opponent_count: int = 5) -> Season:
    rng = random.Random(seed)
    config = LeagueConfig(
        club_name="Player FC",
        opponent_count=opponent_count,
        tier=LeagueTier.SEMI_PRO,
    )
    clubs = generate_season_opponents(rng, count=opponent_count)
    return generate_season(rng, config, clubs)


class TestSeason:
    def test_fixture_count(self):
        s = _make_season(opponent_count=5)
        # 6 teams, round-robin home+away = 30 fixtures.
        assert len(s.fixtures) == 30

    def test_all_club_names(self):
        s = _make_season(opponent_count=5)
        names = s.all_club_names
        assert len(names) == 6
        assert "Player FC" in names

    def test_total_weeks(self):
        s = _make_season(opponent_count=5)
        assert s.total_weeks == 10

    def test_current_fixture(self):
        s = _make_season(opponent_count=5)
        f = s.current_fixture()
        assert f is not None
        assert f.week == 1
        club = s.config.club_name
        assert club in (f.home, f.away)

    def test_fixture_for_every_week(self):
        s = _make_season(opponent_count=5)
        for week in range(1, s.total_weeks + 1):
            f = s.fixture_for_week(week)
            assert f is not None, f"No fixture for week {week}"
            assert s.config.club_name in (f.home, f.away)

    def test_standings_empty_initially(self):
        s = _make_season(opponent_count=3)
        standings = s.standings()
        assert len(standings) == 4  # 3 opponents + player
        for st in standings:
            assert st.played == 0
            assert st.points == 0

    def test_record_result(self):
        s = _make_season(opponent_count=3)
        f = s.record_result(1, 2, 1)
        assert f is not None
        assert f.played
        assert f.home_goals == 2
        assert f.away_goals == 1

    def test_standings_after_results(self):
        s = _make_season(opponent_count=3)
        # Play all fixtures for week 1.
        s.record_result(1, 3, 0)  # Player's match.
        s.simulate_other_results(1, random.Random(99))
        standings = s.standings()
        # Every club involved in week 1 should show 1 game played.
        for st in standings:
            # Some clubs might not play in week 1 (odd count).
            assert st.played <= 1

    def test_player_position(self):
        s = _make_season(opponent_count=3)
        pos = s.player_position()
        assert 1 <= pos <= 4

    def test_simulate_other_results(self):
        s = _make_season(opponent_count=5)
        s.simulate_other_results(1, random.Random(0))
        played = [f for f in s.fixtures if f.played]
        # Should have simulated non-player fixtures for week 1.
        for f in played:
            assert f.week == 1
            assert s.config.club_name not in (f.home, f.away)

    def test_advance_week(self):
        s = _make_season(opponent_count=3)
        assert s.current_week == 1
        s.advance_week()
        assert s.current_week == 2

    def test_is_complete(self):
        s = _make_season(opponent_count=3)
        assert not s.is_complete
        for _ in range(s.total_weeks):
            s.advance_week()
        assert s.is_complete

    def test_opponent_club_by_name(self):
        s = _make_season(opponent_count=3)
        for club in s.clubs:
            found = s.opponent_club_by_name(club.name)
            assert found is not None
            assert found.name == club.name
        assert s.opponent_club_by_name("Nonexistent") is None

    def test_determinism(self):
        s1 = _make_season(seed=42)
        s2 = _make_season(seed=42)
        assert len(s1.fixtures) == len(s2.fixtures)
        for a, b in zip(s1.fixtures, s2.fixtures):
            assert a.home == b.home and a.away == b.away

    def test_different_seeds_diverge(self):
        s1 = _make_season(seed=1)
        s2 = _make_season(seed=2)
        # Club names or fixture order should differ.
        names1 = {c.name for c in s1.clubs}
        names2 = {c.name for c in s2.clubs}
        assert names1 != names2 or [
            (f.home, f.away) for f in s1.fixtures
        ] != [(f.home, f.away) for f in s2.fixtures]


# ---------------------------------------------------------------------------
# Season round-trip (save/load)
# ---------------------------------------------------------------------------


class TestSeasonSerialisation:
    def test_round_trip_empty(self):
        s = _make_season(opponent_count=3)
        d = s.to_dict()
        restored = Season.from_dict(d)
        assert restored.config == s.config
        assert len(restored.clubs) == len(s.clubs)
        assert len(restored.fixtures) == len(s.fixtures)
        assert restored.current_week == s.current_week

    def test_round_trip_with_results(self):
        s = _make_season(opponent_count=3)
        s.record_result(1, 2, 1)
        s.simulate_other_results(1, random.Random(0))
        s.advance_week()

        d = s.to_dict()
        restored = Season.from_dict(d)
        assert restored.current_week == 2
        # Check played fixtures survived.
        played_orig = [f for f in s.fixtures if f.played]
        played_rest = [f for f in restored.fixtures if f.played]
        assert len(played_orig) == len(played_rest)
        for a, b in zip(played_orig, played_rest):
            assert a.home_goals == b.home_goals
            assert a.away_goals == b.away_goals

    def test_round_trip_via_save_module(self):
        """Full save.py round-trip with season on GameState."""
        from engine.events import GameState
        from engine.save import deserialise, serialise

        s = _make_season(opponent_count=3)
        state = GameState(season=s)
        data = serialise(state)
        restored_state, _, _ = deserialise(data)
        assert restored_state.season is not None
        assert restored_state.season.config == s.config
        assert len(restored_state.season.fixtures) == len(s.fixtures)

    def test_legacy_save_no_season(self):
        """Saves without a season field load with season=None."""
        from engine.events import GameState
        from engine.save import deserialise, serialise

        state = GameState()
        assert state.season is None
        data = serialise(state)
        restored, _, _ = deserialise(data)
        assert restored.season is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_club_mean_skill(self):
        club = OpponentClub(
            name="X",
            seeds=[
                TierDSeed(role=CharacterRole.STRIKER, skill_rating=0.6),
                TierDSeed(role=CharacterRole.STRIKER, skill_rating=0.4),
            ],
        )
        assert abs(_club_mean_skill(club) - 0.5) < 1e-9

    def test_club_mean_skill_none(self):
        assert _club_mean_skill(None) == 0.5

    def test_club_mean_skill_empty(self):
        club = OpponentClub(name="Y", seeds=[])
        assert _club_mean_skill(club) == 0.5

    def test_poisson_draw_non_negative(self):
        rng = random.Random(0)
        for _ in range(100):
            assert _poisson_draw(1.5, rng) >= 0

    def test_poisson_draw_mean_converges(self):
        rng = random.Random(42)
        draws = [_poisson_draw(2.0, rng) for _ in range(5000)]
        mean = sum(draws) / len(draws)
        assert 1.5 < mean < 2.5


# ---------------------------------------------------------------------------
# Integration: new_game with league config
# ---------------------------------------------------------------------------


class TestNewGameLeague:
    def test_new_game_creates_season(self):
        from engine.session import GameSession

        session = GameSession.new_game("Test Player", seed=42)
        assert session.state.season is not None
        assert session.state.season.config.club_name == "Ashworth Town"
        assert len(session.state.season.clubs) == 11

    def test_new_game_custom_league(self):
        from engine.session import GameSession

        lc = LeagueConfig(
            club_name="My Club",
            opponent_count=5,
            league_format=LeagueFormat.CLOSED,
            tier=LeagueTier.AMATEUR,
        )
        session = GameSession.new_game(
            "Test Player", seed=42, league_config=lc,
        )
        season = session.state.season
        assert season is not None
        assert season.config.club_name == "My Club"
        assert season.config.league_format == LeagueFormat.CLOSED
        assert season.config.tier == LeagueTier.AMATEUR
        assert len(season.clubs) == 5
        assert season.total_weeks == 10

    def test_legacy_roster_no_season(self):
        """Legacy path (roster=dict) should not create a season."""
        from engine.session import GameSession

        session = GameSession.new_game(
            "Test Player", seed=42, roster={},
        )
        assert session.state.season is None

    def test_new_game_determinism(self):
        from engine.session import GameSession

        s1 = GameSession.new_game("Test", seed=99)
        s2 = GameSession.new_game("Test", seed=99)
        assert s1.state.season is not None
        assert s2.state.season is not None
        names1 = [c.name for c in s1.state.season.clubs]
        names2 = [c.name for c in s2.state.season.clubs]
        assert names1 == names2

    def test_tier_affects_opponent_skill(self):
        from engine.session import GameSession

        pro = GameSession.new_game(
            "P", seed=42,
            league_config=LeagueConfig(tier=LeagueTier.PROFESSIONAL, opponent_count=5),
        )
        am = GameSession.new_game(
            "A", seed=42,
            league_config=LeagueConfig(tier=LeagueTier.AMATEUR, opponent_count=5),
        )
        pro_skills = [
            s.skill_rating
            for c in pro.state.season.clubs
            for s in c.seeds
        ]
        am_skills = [
            s.skill_rating
            for c in am.state.season.clubs
            for s in c.seeds
        ]
        # Professional should have higher mean skill.
        assert sum(pro_skills) / len(pro_skills) > sum(am_skills) / len(am_skills)


# ---------------------------------------------------------------------------
# Session lifecycle with season
# ---------------------------------------------------------------------------


class TestSessionSeasonFlow:
    def _session(self, seed: int = 42) -> "GameSession":
        from engine.session import GameSession

        return GameSession.new_game(
            "Flow Test",
            seed=seed,
            league_config=LeagueConfig(opponent_count=5),
        )

    def test_setup_match_from_season(self):
        s = self._session()
        opp = s.setup_match_from_season()
        assert opp is not None
        assert len(s.opponent) > 0
        assert s._active_match_label is not None
        assert opp in s._active_match_label

    def test_advance_week_advances_season(self):
        s = self._session()
        assert s.state.season.current_week == 1
        s.advance_week()
        assert s.state.season.current_week == 2

    def test_save_round_trip_preserves_season(self):
        from engine.session import GameSession

        s = self._session()
        data = s.serialise()
        restored = GameSession.deserialise(data)
        assert restored.state.season is not None
        assert restored.state.season.config.club_name == s.state.season.config.club_name
        assert len(restored.state.season.fixtures) == len(s.state.season.fixtures)

    def test_setup_match_from_season_no_season(self):
        """Legacy session without season falls back gracefully."""
        from engine.session import GameSession

        s = GameSession.new_game("Test", seed=42, roster={})
        result = s.setup_match_from_season()
        assert result is None
        # Should still have an opponent set up (generic fallback).
        assert len(s.opponent) > 0
