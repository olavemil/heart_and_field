"""Phase simulation — the sports mode (technical §4).

The match is N phases. Each phase samples a per-player performance from a
normal centred on that player's composite, aggregates with a synergy factor,
compares against opponent, updates momentum, and rolls for a goal.

Stamina is the only stat whose contribution decays with fatigue. Other
stats hold up across the match.

All randomness is injected: pass `rng` (a `numpy.random.Generator`) to
anything that draws. Do not call module-level `np.random.*` here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

import numpy as np

from .characters import (
    Character,
    TierACharacter,
    TierBCharacter,
    TierDSeed,
    character_stat,
)
from .motivators import Motivator
from .stats import StatName, clamp


# --- Sport configuration -----------------------------------------------------


class Sport(str, Enum):
    SOCCER = "soccer"
    RUGBY = "rugby"
    BASKETBALL = "basketball"


SPORT_WEIGHTS: dict[Sport, dict[StatName, float]] = {
    Sport.SOCCER: {
        StatName.SPEED: 0.30,
        StatName.STRENGTH: 0.20,
        StatName.FINESSE: 0.30,
        StatName.STAMINA: 0.20,
    },
    Sport.RUGBY: {
        StatName.STRENGTH: 0.35,
        StatName.SPEED: 0.20,
        StatName.FINESSE: 0.15,
        StatName.STAMINA: 0.30,
    },
    Sport.BASKETBALL: {
        StatName.SPEED: 0.30,
        StatName.FINESSE: 0.30,
        StatName.STAMINA: 0.20,
        StatName.STRENGTH: 0.20,
    },
}


# Match-level constants. Tunable; keep them named.
MAX_PHASES_DEFAULT = 8
FATIGUE_DECAY_CAP = 0.4  # stamina contribution loses up to this fraction late-game
PERFORMANCE_STDDEV = 0.15  # per-phase draw width
MOMENTUM_WEIGHT = 0.35
SYNERGY_BASE = 0.9
SYNERGY_RANGE = 0.2  # synergy ∈ [SYNERGY_BASE, SYNERGY_BASE + SYNERGY_RANGE]
GOAL_BASE_PROB = 0.12
GOAL_MOMENTUM_WEIGHT = 0.25
GOAL_OUTLIER_WEIGHT = 0.20
OUTLIER_Z = 2.0


# --- Composites & motivator stacking ----------------------------------------


def motivator_sum(
    motivators: Sequence[Motivator],
    target: StatName,
    phases_elapsed: int = 0,
) -> float:
    """Sum of active motivators pointing at `target`, with decay applied."""
    return sum(
        m.current_value(phases_elapsed)
        for m in motivators
        if m.target_stat == target
    )


def stat_composite(
    character: Character,
    fatigue_factor: float = 1.0,
    sport: Sport = Sport.SOCCER,
) -> float:
    """Weighted blend of sport-relevant stats. Stamina fades with fatigue.

    `fatigue_factor` runs 1.0 → (1 - FATIGUE_DECAY_CAP) across a match; the
    stamina slice of the composite shrinks proportionally.
    """
    weights = SPORT_WEIGHTS[sport]
    raw = 0.0
    for stat, w in weights.items():
        eff_w = w * fatigue_factor if stat is StatName.STAMINA else w
        raw += character_stat(character, stat) * eff_w
    return clamp(raw)


def _opponent_composite(
    opponent: Sequence[Character | TierDSeed],
    sport: Sport,
    fatigue_factor: float,
    rng: np.random.Generator,
) -> float:
    """Collapse an opponent roster to a single scalar.

    Tier D seeds project their stats on demand; Tier A/B read directly.
    """
    if not opponent:
        return 0.5
    vals = []
    weights = SPORT_WEIGHTS[sport]
    for member in opponent:
        if isinstance(member, TierDSeed):
            # Build a composite by projecting the weighted stats.
            seed_r = _rng_to_random(rng)
            v = 0.0
            for stat, w in weights.items():
                eff_w = (
                    w * fatigue_factor if stat is StatName.STAMINA else w
                )
                v += member.project(stat, seed_r) * eff_w
            vals.append(clamp(v))
        else:
            vals.append(stat_composite(member, fatigue_factor, sport))
    return float(np.mean(vals))


def _rng_to_random(rng: np.random.Generator):
    """Adapter so `TierDSeed.project` (which takes a stdlib Random) stays
    reproducible from the same numpy Generator."""
    import random as _random

    seed = int(rng.integers(0, 2**32 - 1))
    return _random.Random(seed)


def compute_synergy(players: Sequence[Character]) -> float:
    """Team cohesion multiplier derived from collaboration + leadership."""
    if not players:
        return SYNERGY_BASE
    collab = float(
        np.mean([character_stat(p, StatName.COLLABORATION) for p in players])
    )
    lead = float(
        np.mean([character_stat(p, StatName.LEADERSHIP) for p in players])
    )
    blend = 0.7 * collab + 0.3 * lead
    return SYNERGY_BASE + SYNERGY_RANGE * blend


# --- Phase result ------------------------------------------------------------


@dataclass
class PhaseResult:
    phase_number: int
    performances: np.ndarray  # per-player, post-motivator, clipped [0, 1]
    composites: np.ndarray  # per-player baseline used for the draw
    team_perf: float
    opp_perf: float
    momentum: float  # post-update, in [-1, 1]
    goal_scored: bool
    goal_scorer_index: int | None
    outliers: list[int] = field(default_factory=list)  # indices with |z| ≥ OUTLIER_Z

    def to_dict(self) -> dict:
        return {
            "phase_number": self.phase_number,
            "performances": self.performances.tolist(),
            "composites": self.composites.tolist(),
            "team_perf": self.team_perf,
            "opp_perf": self.opp_perf,
            "momentum": self.momentum,
            "goal_scored": self.goal_scored,
            "goal_scorer_index": self.goal_scorer_index,
            "outliers": list(self.outliers),
        }


# --- Core phase simulation ---------------------------------------------------


def fatigue_factor(phase_number: int, total_phases: int = MAX_PHASES_DEFAULT) -> float:
    """Stamina contribution multiplier. Monotonically non-increasing."""
    if total_phases <= 0:
        return 1.0
    progress = min(1.0, max(0.0, phase_number / max(1, total_phases - 1)))
    return 1.0 - progress * FATIGUE_DECAY_CAP


def find_outliers(
    performances: np.ndarray, composites: np.ndarray
) -> list[int]:
    """Indices of players whose draw was ≥ OUTLIER_Z stddevs from their baseline."""
    if len(performances) == 0:
        return []
    z = (performances - composites) / PERFORMANCE_STDDEV
    return [int(i) for i, zi in enumerate(z) if abs(zi) >= OUTLIER_Z]


def check_goal(
    momentum: float,
    performances: np.ndarray,
    opp_perf: float,
    rng: np.random.Generator,
) -> tuple[bool, int | None]:
    """Roll for a goal; if yes, pick a scorer weighted by this phase's performance."""
    if len(performances) == 0:
        return False, None
    best = float(performances.max())
    outlier_bonus = max(0.0, best - opp_perf)
    prob = (
        GOAL_BASE_PROB
        + GOAL_MOMENTUM_WEIGHT * max(0.0, momentum)
        + GOAL_OUTLIER_WEIGHT * outlier_bonus
    )
    prob = clamp(prob, 0.0, 0.95)
    if rng.random() >= prob:
        return False, None
    # Weighted scorer selection.
    weights = np.clip(performances, 1e-6, None)
    weights = weights / weights.sum()
    scorer = int(rng.choice(len(performances), p=weights))
    return True, scorer


def simulate_phase(
    players: Sequence[Character],
    opponent: Sequence[Character | TierDSeed],
    phase_number: int,
    momentum: float,
    rng: np.random.Generator,
    *,
    sport: Sport = Sport.SOCCER,
    total_phases: int = MAX_PHASES_DEFAULT,
) -> PhaseResult:
    """Run one phase. Deterministic given `rng`."""
    ff = fatigue_factor(phase_number, total_phases)
    composites = np.array(
        [stat_composite(p, ff, sport) for p in players], dtype=float
    )
    draws = rng.normal(loc=composites, scale=PERFORMANCE_STDDEV)
    # Motivator delta per player — summed over all sport-relevant stats.
    motiv = np.zeros_like(draws)
    for i, p in enumerate(players):
        mv = 0.0
        for stat in SPORT_WEIGHTS[sport]:
            mv += motivator_sum(p.motivators, stat, phase_number)
        motiv[i] = mv
    performances = np.clip(draws + motiv, 0.0, 1.0)

    synergy = compute_synergy(players)
    team_perf = float(performances.mean() * synergy) if len(players) else 0.0
    opp_perf = _opponent_composite(opponent, sport, ff, rng)

    new_momentum = clamp(
        momentum + (team_perf - opp_perf) * MOMENTUM_WEIGHT, -1.0, 1.0
    )
    goal_scored, scorer = check_goal(new_momentum, performances, opp_perf, rng)
    outliers = find_outliers(performances, composites)

    return PhaseResult(
        phase_number=phase_number,
        performances=performances,
        composites=composites,
        team_perf=team_perf,
        opp_perf=opp_perf,
        momentum=new_momentum,
        goal_scored=goal_scored,
        goal_scorer_index=scorer,
        outliers=outliers,
    )


# --- Self-evaluation (technical §4.2) ---------------------------------------


def self_evaluate(
    player: TierACharacter,
    actual_perf: float,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """Returns (perceived_performance, mood_delta).

    Perception is noised by 1 - INTROSPECTION.awareness (the tuple awareness
    on the introspection stat — how accurately the character reads themselves
    in general).

    Mood moves with (perceived - expectation), amplified by insecurity.
    """
    introspection = player.stats.get(StatName.INTROSPECTION)
    noise_scale = 1.0 - (introspection.awareness if introspection else 0.5)
    noise = float(rng.normal(0.0, noise_scale * 0.2))
    perceived = clamp(actual_perf + noise, 0.0, 1.0)

    confidence_val = (
        player.stats[StatName.CONFIDENCE].value
        if StatName.CONFIDENCE in player.stats
        else 0.5
    )
    insecurity = player.insecurity()
    expectation = confidence_val * 0.6 + (1.0 - insecurity) * 0.4
    mood_delta = (perceived - expectation) * (1.0 + insecurity * 0.5)
    return perceived, mood_delta


def team_morale_delta(
    players: Sequence[TierACharacter],
    performances: np.ndarray,
    rng: np.random.Generator,
) -> float:
    """Mean mood delta across the roster, dampened by leadership of top performers.

    Only Tier A characters self-evaluate; others are ignored for morale.
    """
    if len(players) == 0:
        return 0.0
    tier_a = [
        (i, p) for i, p in enumerate(players) if isinstance(p, TierACharacter)
    ]
    if not tier_a:
        return 0.0

    deltas = np.array(
        [self_evaluate(p, float(performances[i]), rng)[1] for i, p in tier_a]
    )
    # Dampen negative swings when high-performing leaders steady the room.
    top_k = np.argsort(performances)[-max(1, len(performances) // 3) :]
    leader_avg = float(
        np.mean(
            [character_stat(players[i], StatName.LEADERSHIP) for i in top_k]
        )
    )
    damp = 1.0 - 0.4 * leader_avg  # strong leaders halve negative swing
    mean_delta = float(deltas.mean())
    if mean_delta < 0:
        mean_delta *= damp
    return mean_delta
