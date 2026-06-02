"""League configuration, season structure, and standings (Phase 20).

Pure data model + logic for a single-division season. The player's club
plays each opponent twice (home + away) across the season. Standings
track wins/draws/losses/goals/points and compute the table.

Design knobs exposed at game start:

- **Sport**: soccer, rugby, basketball (drives stat weights + squad
  composition via ``simulation.Sport``).
- **LeagueFormat**: ``OPEN`` (promotion/relegation) vs ``CLOSED``
  (no movement between tiers).
- **LeagueTier**: ``PROFESSIONAL``, ``SEMI_PRO``, ``AMATEUR`` — shapes
  the opponent skill range and narrative flavour (sponsor pressure vs
  grassroots community).
- **Season length**: derived from opponent count (each opponent played
  twice → ``2 * opponent_count`` match-weeks).

All RNG is injected. Dataclasses round-trip through ``to_dict`` /
``from_dict`` for save compatibility.
"""

from __future__ import annotations

import random as _random
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

from .roster_factory import OpponentClub


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LeagueFormat(str, Enum):
    """Open leagues have promotion/relegation; closed leagues don't."""
    OPEN = "open"
    CLOSED = "closed"


class LeagueTier(str, Enum):
    """Shapes opponent skill range and narrative tone."""
    PROFESSIONAL = "professional"
    SEMI_PRO = "semi_pro"
    AMATEUR = "amateur"


# Skill ranges per tier — (low, high) fed to ``generate_season_opponents``.
TIER_SKILL_RANGES: dict[LeagueTier, tuple[float, float]] = {
    LeagueTier.PROFESSIONAL: (0.45, 0.80),
    LeagueTier.SEMI_PRO: (0.35, 0.65),
    LeagueTier.AMATEUR: (0.25, 0.55),
}


# ---------------------------------------------------------------------------
# League configuration — chosen once at game start
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeagueConfig:
    """Immutable league settings chosen during game setup.

    ``club_name`` is the player's own club. ``opponent_count``
    determines how many clubs the league has (total clubs =
    opponent_count + 1). Season length is ``2 * opponent_count``
    match-weeks (home + away round-robin).
    """

    club_name: str = "Ashworth Town"
    opponent_count: int = 11
    league_format: LeagueFormat = LeagueFormat.OPEN
    tier: LeagueTier = LeagueTier.SEMI_PRO

    @property
    def total_clubs(self) -> int:
        return self.opponent_count + 1

    @property
    def season_weeks(self) -> int:
        """Total match-weeks in a full season (home + away)."""
        return 2 * self.opponent_count

    def to_dict(self) -> dict:
        return {
            "club_name": self.club_name,
            "opponent_count": self.opponent_count,
            "league_format": self.league_format.value,
            "tier": self.tier.value,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "LeagueConfig":
        return cls(
            club_name=str(d.get("club_name", "Ashworth Town")),
            opponent_count=int(d.get("opponent_count", 11)),
            league_format=LeagueFormat(d.get("league_format", "open")),
            tier=LeagueTier(d.get("tier", "semi_pro")),
        )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@dataclass
class Fixture:
    """A single scheduled match.

    ``home`` / ``away`` are club names. The player's club appears as
    one of them. ``played`` flips to True after the match resolves;
    goals are filled in at that point.
    """

    week: int
    home: str
    away: str
    home_goals: int | None = None
    away_goals: int | None = None
    played: bool = False

    @property
    def is_home_for(self) -> str:
        return self.home

    def result_for(self, club: str) -> str | None:
        """Return 'W', 'D', or 'L' from ``club``'s perspective."""
        if not self.played:
            return None
        assert self.home_goals is not None and self.away_goals is not None
        if club == self.home:
            if self.home_goals > self.away_goals:
                return "W"
            elif self.home_goals == self.away_goals:
                return "D"
            return "L"
        elif club == self.away:
            if self.away_goals > self.home_goals:
                return "W"
            elif self.away_goals == self.home_goals:
                return "D"
            return "L"
        return None

    def goals_for(self, club: str) -> int:
        if not self.played or self.home_goals is None or self.away_goals is None:
            return 0
        if club == self.home:
            return self.home_goals
        if club == self.away:
            return self.away_goals
        return 0

    def goals_against(self, club: str) -> int:
        if not self.played or self.home_goals is None or self.away_goals is None:
            return 0
        if club == self.home:
            return self.away_goals
        if club == self.away:
            return self.home_goals
        return 0

    def opponent_of(self, club: str) -> str | None:
        """Return the other club's name, or None if ``club`` isn't in
        this fixture."""
        if club == self.home:
            return self.away
        if club == self.away:
            return self.home
        return None

    def to_dict(self) -> dict:
        return {
            "week": self.week,
            "home": self.home,
            "away": self.away,
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "played": self.played,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "Fixture":
        return cls(
            week=int(d["week"]),
            home=str(d["home"]),
            away=str(d["away"]),
            home_goals=d.get("home_goals"),
            away_goals=d.get("away_goals"),
            played=bool(d.get("played", False)),
        )


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------


@dataclass
class LeagueStanding:
    """Accumulated record for one club."""

    club: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0

    @property
    def points(self) -> int:
        return self.won * 3 + self.drawn

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    @property
    def sort_key(self) -> tuple:
        """Higher is better: points, then GD, then GF."""
        return (self.points, self.goal_difference, self.goals_for)

    def to_dict(self) -> dict:
        return {
            "club": self.club,
            "played": self.played,
            "won": self.won,
            "drawn": self.drawn,
            "lost": self.lost,
            "goals_for": self.goals_for,
            "goals_against": self.goals_against,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "LeagueStanding":
        return cls(
            club=str(d["club"]),
            played=int(d.get("played", 0)),
            won=int(d.get("won", 0)),
            drawn=int(d.get("drawn", 0)),
            lost=int(d.get("lost", 0)),
            goals_for=int(d.get("goals_for", 0)),
            goals_against=int(d.get("goals_against", 0)),
        )


# ---------------------------------------------------------------------------
# Season
# ---------------------------------------------------------------------------


@dataclass
class Season:
    """A full season of fixtures + standings.

    Created once at ``new_game`` time; updated each match-week.
    ``current_week`` is 1-indexed and tracks how far through the
    season we are (not the same as ``GameState.week_phase.week``
    which is the absolute week counter).
    """

    config: LeagueConfig
    clubs: list[OpponentClub]  # opponent clubs (not including player's)
    fixtures: list[Fixture] = field(default_factory=list)
    current_week: int = 1

    @property
    def all_club_names(self) -> list[str]:
        """All clubs in the league including the player's."""
        return [self.config.club_name] + [c.name for c in self.clubs]

    @property
    def total_weeks(self) -> int:
        return self.config.season_weeks

    @property
    def is_complete(self) -> bool:
        return self.current_week > self.total_weeks

    def fixture_for_week(self, week: int) -> Fixture | None:
        """Return the player's fixture for the given match-week."""
        club = self.config.club_name
        for f in self.fixtures:
            if f.week == week and (f.home == club or f.away == club):
                return f
        return None

    def current_fixture(self) -> Fixture | None:
        """The player's fixture for this match-week."""
        return self.fixture_for_week(self.current_week)

    def opponent_club_by_name(self, name: str) -> OpponentClub | None:
        """Look up an opponent club by name."""
        for c in self.clubs:
            if c.name == name:
                return c
        return None

    def standings(self) -> list[LeagueStanding]:
        """Compute the league table from played fixtures.

        Returns standings sorted best-to-worst (points → GD → GF).
        """
        table: dict[str, LeagueStanding] = {
            name: LeagueStanding(club=name) for name in self.all_club_names
        }
        for f in self.fixtures:
            if not f.played:
                continue
            assert f.home_goals is not None and f.away_goals is not None
            for club in (f.home, f.away):
                if club not in table:
                    continue
                s = table[club]
                s.played += 1
                s.goals_for += f.goals_for(club)
                s.goals_against += f.goals_against(club)
                result = f.result_for(club)
                if result == "W":
                    s.won += 1
                elif result == "D":
                    s.drawn += 1
                elif result == "L":
                    s.lost += 1
        return sorted(table.values(), key=lambda s: s.sort_key, reverse=True)

    def player_position(self) -> int:
        """1-indexed league position of the player's club."""
        for i, s in enumerate(self.standings(), 1):
            if s.club == self.config.club_name:
                return i
        return len(self.all_club_names)

    def record_result(
        self,
        week: int,
        home_goals: int,
        away_goals: int,
    ) -> Fixture | None:
        """Record the player's match result for ``week``.

        Returns the updated fixture, or None if not found.
        """
        f = self.fixture_for_week(week)
        if f is None:
            return None
        f.home_goals = home_goals
        f.away_goals = away_goals
        f.played = True
        return f

    def simulate_other_results(self, week: int, rng: _random.Random) -> None:
        """Simulate results for all non-player fixtures in ``week``.

        Uses a simple Poisson-ish model keyed off each club's seed
        skill rating. The player's fixture is skipped (already resolved
        by the match engine).
        """
        club = self.config.club_name
        for f in self.fixtures:
            if f.week != week or f.played:
                continue
            if f.home == club or f.away == club:
                continue
            # Derive expected goals from club skill ratings.
            home_club = self.opponent_club_by_name(f.home)
            away_club = self.opponent_club_by_name(f.away)
            home_skill = _club_mean_skill(home_club)
            away_skill = _club_mean_skill(away_club)
            # Simple model: expected goals ∝ skill, home advantage +0.3.
            home_xg = max(0.3, home_skill * 2.5 + 0.3)
            away_xg = max(0.3, away_skill * 2.5)
            f.home_goals = _poisson_draw(home_xg, rng)
            f.away_goals = _poisson_draw(away_xg, rng)
            f.played = True

    def advance_week(self) -> None:
        """Move to the next match-week."""
        self.current_week += 1

    def to_dict(self) -> dict:
        return {
            "config": self.config.to_dict(),
            "clubs": [_opponent_club_to_dict(c) for c in self.clubs],
            "fixtures": [f.to_dict() for f in self.fixtures],
            "current_week": self.current_week,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "Season":
        from .characters import TierDSeed

        config = LeagueConfig.from_dict(d["config"])
        clubs = [_opponent_club_from_dict(c) for c in d.get("clubs", [])]
        fixtures = [Fixture.from_dict(f) for f in d.get("fixtures", [])]
        return cls(
            config=config,
            clubs=clubs,
            fixtures=fixtures,
            current_week=int(d.get("current_week", 1)),
        )


# ---------------------------------------------------------------------------
# OpponentClub serialisation (deferred from Phase 18B review)
# ---------------------------------------------------------------------------


def _opponent_club_to_dict(club: OpponentClub) -> dict:
    return {
        "name": club.name,
        "seeds": [s.to_dict() for s in club.seeds],
    }


def _opponent_club_from_dict(d: Mapping) -> OpponentClub:
    from .characters import TierDSeed

    return OpponentClub(
        name=str(d["name"]),
        seeds=[TierDSeed.from_dict(s) for s in d.get("seeds", [])],
    )


# ---------------------------------------------------------------------------
# Fixture generation
# ---------------------------------------------------------------------------


def generate_fixtures(
    club_names: list[str],
    rng: _random.Random,
) -> list[Fixture]:
    """Generate a round-robin fixture list (home + away).

    Each pair of clubs meets twice — once at each venue. The schedule
    is shuffled so matches feel varied rather than alphabetically
    ordered. Returns fixtures tagged with week numbers 1..N.
    """
    n = len(club_names)
    if n < 2:
        return []

    # Standard round-robin: (n-1) rounds if n is even, n rounds if odd.
    # We fix club_names[0] and rotate the rest (circle method).
    teams = list(club_names)
    if n % 2 == 1:
        teams.append("__BYE__")
    num_teams = len(teams)
    half = num_teams // 2
    rounds_per_half: list[list[tuple[str, str]]] = []

    # First half: rotate all but teams[0].
    rotating = list(teams[1:])
    for _ in range(num_teams - 1):
        round_pairs: list[tuple[str, str]] = []
        for i in range(half):
            home = teams[0] if i == 0 else rotating[i - 1]
            away = rotating[-(i + 1)] if i == 0 else rotating[num_teams - 2 - i]
            # Skip byes.
            if home == "__BYE__" or away == "__BYE__":
                continue
            round_pairs.append((home, away))
        rounds_per_half.append(round_pairs)
        # Rotate.
        rotating = [rotating[-1]] + rotating[:-1]

    # Second half: mirror with home/away swapped.
    all_rounds = list(rounds_per_half)
    for round_pairs in rounds_per_half:
        all_rounds.append([(away, home) for home, away in round_pairs])

    # Shuffle round order for variety.
    rng.shuffle(all_rounds)

    fixtures: list[Fixture] = []
    for week_num, round_pairs in enumerate(all_rounds, 1):
        for home, away in round_pairs:
            fixtures.append(Fixture(week=week_num, home=home, away=away))
    return fixtures


def generate_season(
    rng: _random.Random,
    config: LeagueConfig,
    clubs: list[OpponentClub],
) -> Season:
    """Build a complete season from config + opponent clubs.

    Generates a round-robin fixture list and returns a ``Season``
    ready for play.
    """
    all_names = [config.club_name] + [c.name for c in clubs]
    fixtures = generate_fixtures(all_names, rng)
    return Season(
        config=config,
        clubs=clubs,
        fixtures=fixtures,
        current_week=1,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _club_mean_skill(club: OpponentClub | None) -> float:
    """Mean skill rating across a club's seeds. Falls back to 0.5."""
    if club is None or not club.seeds:
        return 0.5
    return sum(s.skill_rating for s in club.seeds) / len(club.seeds)


def _poisson_draw(expected: float, rng: _random.Random) -> int:
    """Simple Poisson-like draw for goal scoring.

    Uses the inverse-transform method with stdlib random so we don't
    need numpy here.
    """
    import math

    l_val = math.exp(-expected)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p < l_val:
            break
    return k - 1
