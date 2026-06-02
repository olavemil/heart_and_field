"""Random character generator (Phase 18A).

Pure-Python factory that turns an injected ``random.Random`` into a
fully-populated :class:`TierACharacter` or :class:`TierBCharacter`.
No LLM, no image generation, no module-level RNG — every call is
reproducible from the seed of the rng passed in.

Composition:

- ``generate_name(rng, *, gender_presentation)`` — first/last from
  curated pools.
- ``random_stats_flat(role, rng)`` and ``random_stats_tuple(role, rng)``
  — per-role stat profiles with bounded variance.
- ``random_quirks(rng, *, count_range, role=None)`` — 1–N quirks with
  optional role-aware weighting.
- ``random_descriptor(rng, *, gender_presentation=None)`` — visual
  ``CharacterDescriptor`` axes for the sprite pipeline.
- ``generate_character(role, rng, *, tier, ...)`` — composes the above
  into a complete character.

Every helper accepts overrides so the player customisation flow
(Phase 18D) can pin individual fields without rewriting the factory.
"""

from __future__ import annotations

import random as _random
from typing import Iterable, Literal

from .characters import CharacterRole, Disposition, TierACharacter, TierBCharacter
from .quirks import Quirk, QuirkDomain, QuirkPattern
from .sprite_pool import (
    AgeBucket,
    Build,
    CharacterDescriptor,
    GenderPresentation,
    SkinTone,
)
from .stats import StatName, StatTuple, clamp


# ===========================================================================
# Name pools
# ===========================================================================
#
# Small starter sets that read as contemporary athletic names without
# committing to one cultural register. Authors can swap or extend the
# tuples; the factory reads them by reference at call time so a
# mid-game change takes effect on the next generation.


FIRST_NAMES_MASCULINE: tuple[str, ...] = (
    "Alex", "Sam", "Jordan", "Casey", "Riley", "Marco", "Diego", "Tariq",
    "Yusuf", "Amir", "Kenji", "Hiro", "Lucas", "Mateo", "Eli", "Noah",
    "Jamal", "Felix", "Adrian", "Sebastian", "Idris", "Mikael", "Otis",
    "Caleb", "Theo", "Ronan", "Soren", "Niko", "Ezra", "Levi",
)

FIRST_NAMES_FEMININE: tuple[str, ...] = (
    "Maria", "Sofia", "Aisha", "Yui", "Naomi", "Lena", "Nadia", "Zara",
    "Priya", "Imani", "Mei", "Anya", "Rosa", "Ines", "Saoirse", "Mira",
    "Nora", "Ida", "Lila", "Elena", "Ada", "Bea", "Cleo", "Eve",
    "Freya", "Gia", "Hana", "Iris", "Juno", "Liv",
)

FIRST_NAMES_NEUTRAL: tuple[str, ...] = (
    "Jules", "Charlie", "Robin", "Frankie", "Sasha", "Quinn", "Rowan",
    "Skyler", "Avery", "Kai", "Toby", "Reese",
)

LAST_NAMES: tuple[str, ...] = (
    "Carter", "Lee", "Morgan", "Okonkwo", "Park", "Nakamura", "Vasquez",
    "Doukouré", "Almeida", "Hirsch", "Rasmussen", "Chen", "Singh",
    "Hassan", "Lindqvist", "Kowalski", "Beauvais", "Eriksen", "Chukwu",
    "Petrov", "Yamamoto", "Rojas", "Kovač", "O'Brien", "Diop", "Fenwick",
    "Solberg", "Pereira", "Ferraro", "Volkov",
)


def generate_name(
    rng: _random.Random,
    *,
    gender_presentation: GenderPresentation | None = None,
) -> tuple[str, str]:
    """Draw a (first, last) pair. ``gender_presentation`` biases the
    first-name pool — ``ANDROGYNOUS`` (or ``None``) draws from the
    union of all three pools."""
    if gender_presentation == GenderPresentation.MASCULINE:
        first_pool: tuple[str, ...] = FIRST_NAMES_MASCULINE + FIRST_NAMES_NEUTRAL
    elif gender_presentation == GenderPresentation.FEMININE:
        first_pool = FIRST_NAMES_FEMININE + FIRST_NAMES_NEUTRAL
    else:
        first_pool = (
            FIRST_NAMES_MASCULINE + FIRST_NAMES_FEMININE + FIRST_NAMES_NEUTRAL
        )
    return rng.choice(first_pool), rng.choice(LAST_NAMES)


# ===========================================================================
# Stat profiles per role
# ===========================================================================
#
# Means stored as deltas from a 0.5 baseline so authors can read each
# row at a glance: positive numbers boost, negatives suppress. The
# generator clamps to [0, 1] after applying variance.


_BASE = 0.5


def _profile(**overrides: float) -> dict[StatName, float]:
    profile = {s: _BASE for s in StatName}
    for name, mean in overrides.items():
        profile[StatName[name]] = clamp(_BASE + mean)
    return profile


ROLE_STAT_PROFILES: dict[CharacterRole, dict[StatName, float]] = {
    CharacterRole.STRIKER: _profile(
        SPEED=0.15, FINESSE=0.12, CONFIDENCE=0.10, AGGRESSIVENESS=0.05,
        STAMINA=0.05, MOTIVATION=0.05,
    ),
    CharacterRole.MIDFIELDER: _profile(
        STAMINA=0.10, COLLABORATION=0.10, FINESSE=0.05, REFLECTION=0.05,
        LEADERSHIP=0.05,
    ),
    CharacterRole.DEFENDER: _profile(
        STRENGTH=0.15, CAUTIOUSNESS=0.12, STAMINA=0.05,
        AGGRESSIVENESS=0.05, COLLABORATION=0.05,
    ),
    CharacterRole.GOALKEEPER: _profile(
        FINESSE=0.10, CAUTIOUSNESS=0.10, REFLECTION=0.10, CONFIDENCE=0.05,
        STAMINA=-0.05,
    ),
    CharacterRole.MANAGER: _profile(
        LEADERSHIP=0.20, REFLECTION=0.15, MOTIVATION=0.10, CAUTIOUSNESS=0.05,
    ),
    CharacterRole.ASSISTANT_COACH: _profile(
        LEADERSHIP=0.10, COLLABORATION=0.10, REFLECTION=0.05,
    ),
    CharacterRole.PHYSIO: _profile(
        REFLECTION=0.10, COLLABORATION=0.10, CAUTIOUSNESS=0.10,
    ),
    CharacterRole.MEDIA: _profile(
        CONFIDENCE=0.15, MOTIVATION=0.05, INTROSPECTION=-0.05,
    ),
    CharacterRole.FAMILY: _profile(
        COLLABORATION=0.10, REFLECTION=0.05,
    ),
    CharacterRole.OTHER: _profile(),
}


def _draw_stat_value(mean: float, rng: _random.Random, *, variance: float) -> float:
    """Gaussian-like draw clamped to [0, 1]. Uses a triangular
    distribution centered at ``mean`` with half-width ``variance``
    so we don't depend on numpy here."""
    low = max(0.0, mean - variance)
    high = min(1.0, mean + variance)
    return clamp(rng.triangular(low, high, mean))


def random_stats_flat(
    role: CharacterRole,
    rng: _random.Random,
    *,
    variance: float = 0.12,
) -> dict[StatName, float]:
    """Tier B stats: a flat value per stat drawn around the role's
    profile mean."""
    profile = ROLE_STAT_PROFILES.get(role, ROLE_STAT_PROFILES[CharacterRole.OTHER])
    return {
        stat: _draw_stat_value(mean, rng, variance=variance)
        for stat, mean in profile.items()
    }


def random_stats_tuple(
    role: CharacterRole,
    rng: _random.Random,
    *,
    variance: float = 0.12,
    awareness_range: tuple[float, float] = (0.35, 0.75),
    focus_range: tuple[float, float] = (0.30, 0.70),
) -> dict[StatName, StatTuple]:
    """Tier A stats: a full tuple per stat. Value follows the role
    profile; awareness and focus draw uniformly from their ranges so
    the character has a varied self-knowledge map without coupling to
    skill level."""
    profile = ROLE_STAT_PROFILES.get(role, ROLE_STAT_PROFILES[CharacterRole.OTHER])
    out: dict[StatName, StatTuple] = {}
    for stat, mean in profile.items():
        out[stat] = StatTuple(
            value=_draw_stat_value(mean, rng, variance=variance),
            awareness=clamp(rng.uniform(*awareness_range)),
            focus=clamp(rng.uniform(*focus_range)),
        )
    return out


# ===========================================================================
# Quirks
# ===========================================================================
#
# Role-aware quirk weighting: a striker is more likely PERFORMATIVE,
# a defender more likely RIGID, etc. The lookup is a multiplier on
# the base uniform draw — unmapped roles fall back to flat uniform.


_DEFAULT_DOMAIN_WEIGHT: dict[QuirkDomain, float] = {d: 1.0 for d in QuirkDomain}
_DEFAULT_PATTERN_WEIGHT: dict[QuirkPattern, float] = {p: 1.0 for p in QuirkPattern}


_ROLE_DOMAIN_WEIGHTS: dict[CharacterRole, dict[QuirkDomain, float]] = {
    CharacterRole.STRIKER: {
        **_DEFAULT_DOMAIN_WEIGHT,
        QuirkDomain.PERFORMANCE: 1.6,
        QuirkDomain.EMOTIONAL: 1.2,
    },
    CharacterRole.MIDFIELDER: {
        **_DEFAULT_DOMAIN_WEIGHT,
        QuirkDomain.SOCIAL: 1.5,
        QuirkDomain.COGNITIVE: 1.3,
    },
    CharacterRole.DEFENDER: {
        **_DEFAULT_DOMAIN_WEIGHT,
        QuirkDomain.PHYSICAL: 1.5,
        QuirkDomain.COGNITIVE: 1.3,
    },
    CharacterRole.GOALKEEPER: {
        **_DEFAULT_DOMAIN_WEIGHT,
        QuirkDomain.COGNITIVE: 1.6,
        QuirkDomain.EMOTIONAL: 1.4,
    },
    CharacterRole.MANAGER: {
        **_DEFAULT_DOMAIN_WEIGHT,
        QuirkDomain.SOCIAL: 1.4,
        QuirkDomain.COGNITIVE: 1.5,
    },
}


_ROLE_PATTERN_WEIGHTS: dict[CharacterRole, dict[QuirkPattern, float]] = {
    CharacterRole.STRIKER: {
        **_DEFAULT_PATTERN_WEIGHT,
        QuirkPattern.PERFORMATIVE: 1.6,
        QuirkPattern.SEEKING: 1.3,
    },
    CharacterRole.DEFENDER: {
        **_DEFAULT_PATTERN_WEIGHT,
        QuirkPattern.RIGID: 1.5,
        QuirkPattern.AVOIDANT: 1.2,
    },
    CharacterRole.GOALKEEPER: {
        **_DEFAULT_PATTERN_WEIGHT,
        QuirkPattern.COMPULSIVE: 1.6,
        QuirkPattern.RIGID: 1.4,
    },
}


def _weighted_choice(
    rng: _random.Random,
    items: Iterable,
    weights: dict,
):
    items_list = list(items)
    weights_list = [weights.get(item, 1.0) for item in items_list]
    return rng.choices(items_list, weights=weights_list, k=1)[0]


def random_quirks(
    rng: _random.Random,
    *,
    count_range: tuple[int, int] = (1, 2),
    role: CharacterRole | None = None,
) -> list[Quirk]:
    """Draw 1–N unique quirks for a character.

    Same ``(domain, pattern)`` pair never repeats — duplicate rolls
    are silently re-drawn until uniqueness or the cap is reached. The
    counts default range (1, 2) keeps most characters lightly flavoured
    and avoids over-stacking quirk effects.
    """
    domain_weights = (
        _ROLE_DOMAIN_WEIGHTS.get(role, _DEFAULT_DOMAIN_WEIGHT)
        if role is not None
        else _DEFAULT_DOMAIN_WEIGHT
    )
    pattern_weights = (
        _ROLE_PATTERN_WEIGHTS.get(role, _DEFAULT_PATTERN_WEIGHT)
        if role is not None
        else _DEFAULT_PATTERN_WEIGHT
    )

    low, high = count_range
    count = rng.randint(low, high)
    seen: set[tuple[QuirkDomain, QuirkPattern]] = set()
    out: list[Quirk] = []
    # Cap retries so a degenerate weight table doesn't loop forever.
    max_attempts = count * 8
    for _ in range(max_attempts):
        if len(out) >= count:
            break
        domain = _weighted_choice(rng, QuirkDomain, domain_weights)
        pattern = _weighted_choice(rng, QuirkPattern, pattern_weights)
        key = (domain, pattern)
        if key in seen:
            continue
        seen.add(key)
        out.append(Quirk(domain=domain, pattern=pattern))
    return out


# Disposition-themed quirk pools. When the player picks a disposition
# during character creation, this table selects thematic quirks instead
# of purely random ones. Each entry is a list of candidate quirks —
# ``quirks_for_disposition`` draws 1–2 from the list.

_DISPOSITION_QUIRKS: dict[Disposition, list[Quirk]] = {
    Disposition.CALM: [
        Quirk(domain=QuirkDomain.EMOTIONAL, pattern=QuirkPattern.AVOIDANT),
        Quirk(domain=QuirkDomain.COGNITIVE, pattern=QuirkPattern.RIGID),
        Quirk(domain=QuirkDomain.SOCIAL, pattern=QuirkPattern.AVOIDANT),
    ],
    Disposition.FIERY: [
        Quirk(domain=QuirkDomain.EMOTIONAL, pattern=QuirkPattern.REACTIVE),
        Quirk(domain=QuirkDomain.PERFORMANCE, pattern=QuirkPattern.COMPULSIVE),
        Quirk(domain=QuirkDomain.SOCIAL, pattern=QuirkPattern.REACTIVE),
    ],
    Disposition.GUARDED: [
        Quirk(domain=QuirkDomain.SOCIAL, pattern=QuirkPattern.AVOIDANT),
        Quirk(domain=QuirkDomain.EMOTIONAL, pattern=QuirkPattern.RIGID),
        Quirk(domain=QuirkDomain.COGNITIVE, pattern=QuirkPattern.AVOIDANT),
    ],
    Disposition.WARM: [
        Quirk(domain=QuirkDomain.SOCIAL, pattern=QuirkPattern.SEEKING),
        Quirk(domain=QuirkDomain.EMOTIONAL, pattern=QuirkPattern.SEEKING),
        Quirk(domain=QuirkDomain.PERFORMANCE, pattern=QuirkPattern.PERFORMATIVE),
    ],
    Disposition.COMPETITIVE: [
        Quirk(domain=QuirkDomain.PERFORMANCE, pattern=QuirkPattern.COMPULSIVE),
        Quirk(domain=QuirkDomain.COGNITIVE, pattern=QuirkPattern.REACTIVE),
        Quirk(domain=QuirkDomain.PHYSICAL, pattern=QuirkPattern.SEEKING),
    ],
    Disposition.WITHDRAWN: [
        Quirk(domain=QuirkDomain.SOCIAL, pattern=QuirkPattern.AVOIDANT),
        Quirk(domain=QuirkDomain.EMOTIONAL, pattern=QuirkPattern.AVOIDANT),
        Quirk(domain=QuirkDomain.COGNITIVE, pattern=QuirkPattern.RIGID),
    ],
}


def quirks_for_disposition(
    disposition: Disposition,
    rng: _random.Random,
    *,
    count_range: tuple[int, int] = (1, 2),
) -> list[Quirk]:
    """Draw thematic quirks matching a disposition."""
    pool = _DISPOSITION_QUIRKS.get(disposition, [])
    if not pool:
        return random_quirks(rng, count_range=count_range)
    count = rng.randint(*count_range)
    count = min(count, len(pool))
    return rng.sample(pool, k=count)


# ===========================================================================
# Visual descriptor
# ===========================================================================


_HAIR_TOKENS: tuple[str, ...] = (
    "short_brown", "short_black", "short_blonde", "short_red", "short_grey",
    "long_brown", "long_black", "long_blonde", "long_red", "long_grey",
    "buzz_brown", "buzz_black", "curly_brown", "curly_black",
    "wavy_brown", "wavy_blonde",
)


def random_descriptor(
    rng: _random.Random,
    *,
    gender_presentation: GenderPresentation | None = None,
    age_bucket: AgeBucket | None = None,
) -> CharacterDescriptor:
    """Random visual descriptor — every axis drawn uniformly unless
    pinned by an override."""
    return CharacterDescriptor(
        gender_presentation=(
            gender_presentation
            if gender_presentation is not None
            else rng.choice(list(GenderPresentation))
        ),
        age_bucket=(
            age_bucket if age_bucket is not None
            else rng.choice(list(AgeBucket))
        ),
        skin_tone=rng.choice(list(SkinTone)),
        build=rng.choice(list(Build)),
        hair=rng.choice(_HAIR_TOKENS),
        facial_hair=bool(rng.random() < 0.30),
        glasses=bool(rng.random() < 0.15),
    )


# ===========================================================================
# Composition
# ===========================================================================


def generate_character(
    role: CharacterRole,
    rng: _random.Random,
    *,
    tier: Literal["A", "B"] = "B",
    character_id: str | None = None,
    name: tuple[str, str] | None = None,
    descriptor: CharacterDescriptor | None = None,
    quirk_count_range: tuple[int, int] = (1, 2),
    quirks: list[Quirk] | None = None,
):
    """Compose a full character from the helpers above.

    ``character_id`` defaults to a slugified ``first_last`` so two
    characters with the same name never collide on id. Callers
    needing a stable id (placeholder resolution, marquee characters)
    pass it explicitly.

    Returns a :class:`TierACharacter` or :class:`TierBCharacter`
    depending on ``tier``.
    """
    chosen_descriptor = (
        descriptor if descriptor is not None
        else random_descriptor(rng)
    )
    if name is None:
        name = generate_name(
            rng,
            gender_presentation=chosen_descriptor.gender_presentation,
        )
    first, last = name
    full_name = f"{first} {last}"
    cid = character_id or _slug_id(first, last, rng)
    chosen_quirks = (
        list(quirks) if quirks is not None
        else random_quirks(rng, count_range=quirk_count_range, role=role)
    )

    gender_str = chosen_descriptor.gender_presentation.value

    if tier == "A":
        return TierACharacter(
            id=cid,
            name=full_name,
            role=role,
            stats=random_stats_tuple(role, rng),
            quirks=chosen_quirks,
            gender_presentation=gender_str,
        )
    return TierBCharacter(
        id=cid,
        name=full_name,
        role=role,
        stats=random_stats_flat(role, rng),
        quirks=chosen_quirks,
        gender_presentation=gender_str,
    )


def _slug_id(first: str, last: str, rng: _random.Random) -> str:
    """Build a slug like ``"alex_carter_3f2a1b"`` — name fragments plus a
    rng-derived suffix so duplicate names get distinct ids."""
    base = f"{first.lower()}_{last.lower()}".replace(" ", "_")
    suffix = format(rng.randint(0, 0xFFFFFF), "06x")
    return f"{base}_{suffix}"
