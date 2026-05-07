"""Roster + opponent seed builder (Phase 18B).

Composes :func:`engine.character_factory.generate_character` into the
units the rest of the engine actually consumes:

- A squad of TierB teammates with a sport-aware role distribution.
- A coaching staff (manager + physio).
- An optional Tier A player for marquee narrative arcs.
- A Tier D opponent seed bank with a named club.

Every helper takes an injected ``random.Random`` so a single seed
reproduces an identical world. The Phase 18D ``new_game`` integration
will pass through one master seed; this module never reaches for a
module-level RNG.
"""

from __future__ import annotations

import random as _random
from dataclasses import dataclass, field
from typing import Iterable

from .character_factory import generate_character, generate_name
from .characters import CharacterRole, Disposition, TierACharacter, TierBCharacter, TierDSeed
from .simulation import Sport
from .sprite_pool import GenderPresentation


# ===========================================================================
# Squad composition
# ===========================================================================


@dataclass(frozen=True)
class SquadComposition:
    """How many of each role belong on the team. Bench / reserve
    counts are folded into the role totals — the simulation doesn't
    distinguish starters from bench at this phase, so the squad is
    one flat roster.
    """

    role_counts: dict[CharacterRole, int]

    def total(self) -> int:
        return sum(self.role_counts.values())


# Per-sport defaults. Soccer authored explicitly; the others get
# proportional fallbacks so adding a sport doesn't break the factory.
SOCCER_DEFAULT = SquadComposition(role_counts={
    CharacterRole.GOALKEEPER: 2,   # 1 starter + 1 backup
    CharacterRole.DEFENDER:   5,
    CharacterRole.MIDFIELDER: 5,
    CharacterRole.STRIKER:    3,
})


_SPORT_COMPOSITIONS: dict[Sport, SquadComposition] = {
    Sport.SOCCER: SOCCER_DEFAULT,
    Sport.RUGBY: SquadComposition(role_counts={
        CharacterRole.GOALKEEPER: 0,  # rugby has no GK
        CharacterRole.DEFENDER:   6,  # forwards
        CharacterRole.MIDFIELDER: 4,
        CharacterRole.STRIKER:    5,  # backs
    }),
    Sport.BASKETBALL: SquadComposition(role_counts={
        CharacterRole.GOALKEEPER: 0,
        CharacterRole.DEFENDER:   3,
        CharacterRole.MIDFIELDER: 3,
        CharacterRole.STRIKER:    4,
    }),
}


def default_squad_composition(sport: Sport = Sport.SOCCER) -> SquadComposition:
    """Return the authored composition for ``sport``. Soccer is the
    canonical default; other sports get their authored shape, falling
    back to soccer for unknown enum extensions."""
    return _SPORT_COMPOSITIONS.get(sport, SOCCER_DEFAULT)


# ===========================================================================
# Roster
# ===========================================================================


@dataclass
class Roster:
    """A complete generated cast — every Phase 18C/18D entry point
    reads a Roster and dispatches.

    ``player`` is optional so test setups (and possibly some game
    modes) can build squads without a focal Tier A character.
    """

    player: TierACharacter | None
    teammates: list[TierBCharacter]
    coaching_staff: list[TierBCharacter]

    def all_characters(self) -> list:
        out: list = []
        if self.player is not None:
            out.append(self.player)
        out.extend(self.teammates)
        out.extend(self.coaching_staff)
        return out

    def by_id(self) -> dict[str, object]:
        return {c.id: c for c in self.all_characters()}


def generate_roster(
    rng: _random.Random,
    *,
    composition: SquadComposition | None = None,
    sport: Sport = Sport.SOCCER,
    with_player: bool = True,
    player_role: CharacterRole = CharacterRole.STRIKER,
    player_name: tuple[str, str] | None = None,
    player_id: str = "player",
) -> Roster:
    """Build a full squad + coaching staff.

    The player (when included) is a Tier A character with the stable
    id ``"player"`` so the rest of the engine and content can refer to
    them without resolving a placeholder. Teammates and staff are
    Tier B, ids derived from name slugs.
    """
    composition = composition or default_squad_composition(sport)

    teammates: list[TierBCharacter] = []
    for role, count in composition.role_counts.items():
        for _ in range(count):
            teammates.append(generate_character(role, rng))

    staff = generate_coaching_staff(rng)

    player: TierACharacter | None = None
    if with_player:
        player = generate_character(
            player_role,
            rng,
            tier="A",
            character_id=player_id,
            name=player_name,
        )

    return Roster(player=player, teammates=teammates, coaching_staff=staff)


# ===========================================================================
# Coaching staff
# ===========================================================================


def generate_coaching_staff(rng: _random.Random) -> list[TierBCharacter]:
    """Generate the canonical coaching staff: a manager + a physio.

    Authors can extend by adding more calls to ``generate_character``
    in their own genesis flow; this default keeps the cast small
    enough that every staff member feels named rather than
    set-dressing.
    """
    manager = generate_character(CharacterRole.MANAGER, rng)
    physio = generate_character(CharacterRole.PHYSIO, rng)
    return [manager, physio]


# ===========================================================================
# Opponents — Tier D seeds + named club
# ===========================================================================


# Compact club name pool. Authors swap or extend; the factory reads at
# call time so a mid-game change takes effect immediately.
CLUB_NAMES: tuple[str, ...] = (
    "Northgate FC", "Westborough United", "St. Hadrian's", "Rivermouth Rovers",
    "Crown Heights Athletic", "Old Kelvin", "Avalon City", "Riverside Wanderers",
    "Cardinal Park", "Eastvale", "Ironbridge", "Marshfield",
    "Pelham Albion", "Stonecliff", "Tarrant Town", "Whitestone",
    "Greycoat Athletic", "Brackenwood", "Halverson FC", "Linfield United",
    "Nordskov", "Aldenburg", "Castelmonte", "Porto Verde",
)


@dataclass(frozen=True)
class OpponentClub:
    """A named opponent with a deterministic Tier D seed roster.

    Seed list lives on the club so a fixture against the same club
    later in the season uses the same roster identity (rebuilt from
    the same rng path)."""

    name: str
    seeds: list[TierDSeed]


_OPPONENT_DISPOSITIONS = (
    Disposition.CALM,
    Disposition.FIERY,
)


def generate_opponent_seed(
    rng: _random.Random,
    *,
    name: str | None = None,
    composition: SquadComposition | None = None,
    sport: Sport = Sport.SOCCER,
    skill_mean: float = 0.5,
    skill_variance: float = 0.12,
) -> OpponentClub:
    """Generate a named opponent club with a Tier D roster.

    ``skill_mean`` and ``skill_variance`` shape the squad's overall
    quality — lower-rated clubs sit around 0.4, top-flight rivals
    around 0.7. ``name`` defaults to a draw from ``CLUB_NAMES``.
    """
    composition = composition or default_squad_composition(sport)
    chosen_name = name if name is not None else rng.choice(CLUB_NAMES)
    seeds: list[TierDSeed] = []
    for role, count in composition.role_counts.items():
        for _ in range(count):
            skill = max(
                0.0,
                min(1.0, rng.gauss(skill_mean, skill_variance)),
            )
            seeds.append(TierDSeed(
                role=role,
                skill_rating=skill,
                form_trend=rng.uniform(-0.3, 0.3),
                disposition=rng.choice(_OPPONENT_DISPOSITIONS),
            ))
    return OpponentClub(name=chosen_name, seeds=seeds)


def generate_season_opponents(
    rng: _random.Random,
    *,
    count: int,
    sport: Sport = Sport.SOCCER,
    skill_range: tuple[float, float] = (0.35, 0.7),
) -> list[OpponentClub]:
    """Generate ``count`` distinct opponent clubs for a season.

    Each club is drawn with a different ``skill_mean`` so the league
    has a spread of difficulty — top-of-table opponents push toward
    the high end of ``skill_range``, bottom-of-table toward the low.
    Names are drawn without replacement so two clubs never share an
    identity.
    """
    if count > len(CLUB_NAMES):
        raise ValueError(
            f"requested {count} opponent clubs but only {len(CLUB_NAMES)} "
            f"club names are authored"
        )
    chosen_names = rng.sample(CLUB_NAMES, count)
    low, high = skill_range
    clubs: list[OpponentClub] = []
    for i, club_name in enumerate(chosen_names):
        # Spread skill_mean linearly across the range so the league
        # has both contenders and strugglers.
        if count == 1:
            skill_mean = (low + high) / 2
        else:
            skill_mean = low + (high - low) * (i / (count - 1))
        clubs.append(generate_opponent_seed(
            rng, name=club_name, sport=sport, skill_mean=skill_mean,
        ))
    return clubs
