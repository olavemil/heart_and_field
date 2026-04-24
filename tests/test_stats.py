import random
import statistics

import pytest

from engine.stats import (
    OBSERVABLE_FORMULAS,
    ObservableName,
    StatName,
    StatTuple,
    clamp,
    compute_observable,
)


def test_clamp_bounds():
    assert clamp(-1) == 0.0
    assert clamp(2.0) == 1.0
    assert clamp(0.5) == 0.5


def test_stat_tuple_perceived_exact_when_aware():
    """Full awareness collapses perception noise to zero."""
    rng = random.Random(0)
    t = StatTuple(value=0.6, awareness=1.0, focus=0.5)
    for _ in range(50):
        assert t.perceived(rng) == pytest.approx(0.6)


def test_stat_tuple_perceived_noisier_when_unaware():
    """Lower awareness → wider spread of self-reads."""
    aware = StatTuple(value=0.5, awareness=0.95, focus=0.5)
    unaware = StatTuple(value=0.5, awareness=0.1, focus=0.5)
    rng_a = random.Random(1)
    rng_u = random.Random(1)
    spread_a = statistics.stdev(aware.perceived(rng_a) for _ in range(400))
    spread_u = statistics.stdev(unaware.perceived(rng_u) for _ in range(400))
    assert spread_u > spread_a * 3


def test_stat_tuple_acted_on_negative_weight_inverts():
    t = StatTuple(value=0.8, awareness=0.5, focus=0.5, weight=-1.0)
    assert t.acted_on(0.8) == pytest.approx(-0.8)


def test_stat_tuple_roundtrip():
    t = StatTuple(value=0.3, awareness=0.7, focus=0.9, weight=-0.5)
    assert StatTuple.from_dict(t.to_dict()) == t


def _uniform_stats(value: float = 0.5) -> dict[StatName, float]:
    return {s: value for s in StatName}


def test_all_observables_covered():
    """Every ObservableName has a formula."""
    assert set(OBSERVABLE_FORMULAS.keys()) == set(ObservableName)


def test_observables_clamp_to_unit_interval():
    """Random stat configs never push observables outside [0, 1]."""
    rng = random.Random(42)
    for _ in range(200):
        stats = {s: rng.random() for s in StatName}
        for obs in ObservableName:
            v = compute_observable(stats, obs)
            assert 0.0 <= v <= 1.0


def test_arrogance_peaks_on_unchecked_confidence():
    """High confidence + low introspection + low insecurity = high arrogance."""
    stats = _uniform_stats(0.5)
    stats[StatName.CONFIDENCE] = 1.0
    stats[StatName.INTROSPECTION] = 0.0
    stats[StatName.INSECURITY] = 0.0
    assert compute_observable(stats, ObservableName.ARROGANCE) == pytest.approx(1.0)


def test_warmth_zero_when_defensive():
    stats = _uniform_stats(1.0)
    stats[StatName.DEFENSIVENESS] = 1.0
    assert compute_observable(stats, ObservableName.WARMTH) == pytest.approx(0.0)


def test_coachability_requires_low_defensiveness():
    stats = _uniform_stats(0.8)
    stats[StatName.DEFENSIVENESS] = 1.0
    assert compute_observable(stats, ObservableName.COACHABILITY) == pytest.approx(0.0)
