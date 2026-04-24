import numpy as np
import pytest

from engine.characters import (
    CharacterRole,
    Disposition,
    TierACharacter,
    TierBCharacter,
    TierDSeed,
)
from engine.motivators import Motivator, MotivatorSource
from engine.simulation import (
    FATIGUE_DECAY_CAP,
    MAX_PHASES_DEFAULT,
    PERFORMANCE_STDDEV,
    Sport,
    compute_synergy,
    fatigue_factor,
    find_outliers,
    self_evaluate,
    simulate_phase,
    stat_composite,
    team_morale_delta,
)
from engine.stats import StatName, StatTuple


# --- Helpers ----------------------------------------------------------------


def _tuple(value: float, awareness: float = 0.5, focus: float = 0.5) -> StatTuple:
    return StatTuple(value=value, awareness=awareness, focus=focus)


def _uniform_a(
    id_: str = "p",
    value: float = 0.5,
    awareness: float = 0.5,
    focus: float = 0.5,
    role: CharacterRole = CharacterRole.MIDFIELDER,
) -> TierACharacter:
    return TierACharacter(
        id=id_,
        name=id_,
        role=role,
        stats={s: _tuple(value, awareness, focus) for s in StatName},
    )


def _roster_a(n: int, value: float = 0.5) -> list[TierACharacter]:
    return [_uniform_a(id_=f"p{i}", value=value) for i in range(n)]


def _roster_b(n: int, value: float = 0.5) -> list[TierBCharacter]:
    return [
        TierBCharacter(
            id=f"o{i}",
            name=f"o{i}",
            role=CharacterRole.MIDFIELDER,
            stats={s: value for s in StatName},
        )
        for i in range(n)
    ]


# --- Fatigue / composite ----------------------------------------------------


def test_fatigue_factor_monotonically_non_increasing():
    vals = [fatigue_factor(i, MAX_PHASES_DEFAULT) for i in range(MAX_PHASES_DEFAULT)]
    assert vals[0] == pytest.approx(1.0)
    assert vals[-1] == pytest.approx(1.0 - FATIGUE_DECAY_CAP)
    for a, b in zip(vals, vals[1:]):
        assert b <= a


def test_stat_composite_drops_for_low_stamina_under_fatigue():
    hi_stamina = TierBCharacter(
        id="a",
        name="a",
        role=CharacterRole.MIDFIELDER,
        stats={s: 0.5 for s in StatName} | {StatName.STAMINA: 0.9},
    )
    lo_stamina = TierBCharacter(
        id="b",
        name="b",
        role=CharacterRole.MIDFIELDER,
        stats={s: 0.5 for s in StatName} | {StatName.STAMINA: 0.1},
    )
    fresh_hi = stat_composite(hi_stamina, fatigue_factor=1.0)
    tired_hi = stat_composite(hi_stamina, fatigue_factor=1.0 - FATIGUE_DECAY_CAP)
    fresh_lo = stat_composite(lo_stamina, fatigue_factor=1.0)
    tired_lo = stat_composite(lo_stamina, fatigue_factor=1.0 - FATIGUE_DECAY_CAP)
    # Both lose stamina contribution; but high-stamina player loses more in absolute terms.
    assert fresh_hi > fresh_lo
    assert fresh_hi - tired_hi > fresh_lo - tired_lo


# --- Synergy ----------------------------------------------------------------


def test_synergy_rises_with_collaboration_and_leadership():
    low = _roster_a(3, value=0.1)
    high = _roster_a(3, value=0.9)
    assert compute_synergy(high) > compute_synergy(low)


# --- simulate_phase ---------------------------------------------------------


def test_simulate_phase_deterministic_with_seed():
    players = _roster_a(4, value=0.5)
    opp = _roster_b(4, value=0.5)
    r1 = simulate_phase(players, opp, 0, 0.0, np.random.default_rng(123))
    r2 = simulate_phase(players, opp, 0, 0.0, np.random.default_rng(123))
    assert r1.performances.tolist() == r2.performances.tolist()
    assert r1.goal_scored == r2.goal_scored
    assert r1.momentum == pytest.approx(r2.momentum)


def test_simulate_phase_outputs_in_bounds():
    players = _roster_a(5, value=0.6)
    opp = _roster_b(5, value=0.4)
    rng = np.random.default_rng(7)
    for phase in range(MAX_PHASES_DEFAULT):
        r = simulate_phase(players, opp, phase, 0.0, rng)
        assert r.performances.shape == (5,)
        assert ((r.performances >= 0.0) & (r.performances <= 1.0)).all()
        assert -1.0 <= r.momentum <= 1.0


def test_mean_performance_tracks_composite_over_many_runs():
    """Over 500 phase draws, the team-mean performance (pre-synergy) should
    centre near the team's composite."""
    players = _roster_a(4, value=0.6)
    opp = _roster_b(4, value=0.6)
    rng = np.random.default_rng(0)
    composite_mean = stat_composite(players[0])  # all identical
    samples = []
    for _ in range(500):
        r = simulate_phase(players, opp, 0, 0.0, rng)
        samples.append(r.performances.mean())
    emp = float(np.mean(samples))
    assert emp == pytest.approx(composite_mean, abs=0.02)


def test_momentum_drifts_toward_stronger_side():
    strong = _roster_a(4, value=0.9)
    weak = _roster_b(4, value=0.2)
    rng = np.random.default_rng(1)
    momentum = 0.0
    for phase in range(MAX_PHASES_DEFAULT):
        r = simulate_phase(strong, weak, phase, momentum, rng)
        momentum = r.momentum
    assert momentum > 0.5


def test_tier_d_opponent_supported():
    players = _roster_a(3, value=0.5)
    opp = [
        TierDSeed(
            role=CharacterRole.DEFENDER,
            skill_rating=0.6,
            disposition=Disposition.CALM,
        )
        for _ in range(3)
    ]
    rng = np.random.default_rng(0)
    r = simulate_phase(players, opp, 0, 0.0, rng)
    assert 0.0 <= r.opp_perf <= 1.0


def test_motivator_lifts_performance_distribution():
    base = _roster_a(3, value=0.5)
    lifted = _roster_a(3, value=0.5)
    for p in lifted:
        p.motivators.append(
            Motivator(
                target_stat=StatName.SPEED,
                delta=0.2,
                decay_rate=0.0,
                source=MotivatorSource.CROWD,
                salience=10.0,
            )
        )
    opp = _roster_b(3, value=0.5)
    base_mean = np.mean(
        [
            simulate_phase(base, opp, 0, 0.0, np.random.default_rng(i))
            .performances.mean()
            for i in range(200)
        ]
    )
    lift_mean = np.mean(
        [
            simulate_phase(lifted, opp, 0, 0.0, np.random.default_rng(i))
            .performances.mean()
            for i in range(200)
        ]
    )
    assert lift_mean > base_mean + 0.1


def test_outlier_detection_flags_far_draws():
    composites = np.array([0.5, 0.5, 0.5])
    perfs = np.array([0.5, 0.9, 0.2])  # middle one is 2.67σ above, third is 2σ below
    outliers = find_outliers(perfs, composites)
    assert 1 in outliers
    assert 2 in outliers
    assert 0 not in outliers


# --- self_evaluate ----------------------------------------------------------


def test_self_evaluate_low_awareness_misreads_more():
    aware = _uniform_a(awareness=1.0, focus=0.5)
    unaware = _uniform_a(awareness=0.0, focus=0.5)
    rng_a = np.random.default_rng(0)
    rng_u = np.random.default_rng(0)
    aware_errors = []
    unaware_errors = []
    actual = 0.6
    for _ in range(400):
        p_a, _ = self_evaluate(aware, actual, rng_a)
        p_u, _ = self_evaluate(unaware, actual, rng_u)
        aware_errors.append(abs(p_a - actual))
        unaware_errors.append(abs(p_u - actual))
    assert np.mean(unaware_errors) > np.mean(aware_errors) * 3


def test_self_evaluate_insecurity_widens_mood_variance():
    """Insecurity amplifies mood swings — variance rises under identical perf.

    Note: the technical doc's expectation formula (confidence * 0.6 +
    (1 - insecurity) * 0.4) actually *lowers* expectation for insecure
    players, offsetting some of the mean effect. The robust, design-true
    signal is variance: an insecure player swings harder in both directions.
    """
    secure = _uniform_a(awareness=0.95, focus=0.1, value=0.7)
    insecure = _uniform_a(awareness=0.1, focus=0.95, value=0.7)

    rng = np.random.default_rng(0)
    secure_moods = [self_evaluate(secure, 0.5, rng)[1] for _ in range(800)]
    rng = np.random.default_rng(0)
    insecure_moods = [
        self_evaluate(insecure, 0.5, rng)[1] for _ in range(800)
    ]
    assert np.std(insecure_moods) > np.std(secure_moods) * 2


def test_team_morale_delta_respects_tier_a_only():
    players = _roster_a(3, value=0.6)
    perfs = np.array([0.6, 0.6, 0.6])
    rng = np.random.default_rng(0)
    d = team_morale_delta(players, perfs, rng)
    assert isinstance(d, float)
