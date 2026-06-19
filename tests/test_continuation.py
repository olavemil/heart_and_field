"""Tests for engine.continuation — perturbation cascade (Phase 25.4)."""

from __future__ import annotations

import random

from engine.continuation import (
    CONTINUATION_AXES,
    drift_axes,
    drift_probability,
)


def _distribution(n=40000, **kw):
    rng = random.Random(20240619)
    counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    for _ in range(n):
        counts[len(drift_axes(rng, **kw))] += 1
    return {k: v / n for k, v in counts.items()}


class TestDriftProbability:
    def test_diminishes_with_changes(self):
        assert drift_probability(0) == 0.75
        assert drift_probability(1) == 0.5
        assert drift_probability(2) == 0.375
        # strictly decreasing
        ps = [drift_probability(k) for k in range(5)]
        assert all(a > b for a, b in zip(ps, ps[1:]))


class TestDriftCascade:
    def test_deterministic_under_fixed_rng(self):
        a = [drift_axes(random.Random(7)) for _ in range(5)]
        b = [drift_axes(random.Random(7)) for _ in range(5)]
        assert a == b

    def test_drifted_axes_are_valid(self):
        rng = random.Random(1)
        for _ in range(200):
            assert drift_axes(rng).issubset(set(CONTINUATION_AXES))

    def test_distribution_matches_intended_shape(self):
        # ~25% no-drift, mode at 1, mostly 0-2, light tail. (Stopping at the
        # first hold is what produces this; checking all axes would not.)
        d = _distribution()
        assert 0.23 <= d[0] <= 0.27          # ~25% no drift
        assert 0.35 <= d[1] <= 0.40          # ~37.5% one axis
        assert 0.21 <= d[2] <= 0.26          # ~23% two axes
        assert d[0] + d[1] + d[2] >= 0.84    # mostly <= 2
        assert d[1] == max(d.values())       # mode at one
        assert d[4] < d[3] < d[2]            # monotone tail

    def test_forced_change_raises_the_bar(self):
        # drift_axes returns the *additional* cascade drifts. With one drift
        # already forced by the outcome, the cascade starts at the
        # diminished probability (0.5), so "no further drift" is far more
        # likely than from a cold start.
        forced = _distribution(forced_changes=1)  # len == extra drifts
        cold = _distribution()
        assert abs(forced[0] - 0.5) < 0.03   # P(no further drift) ≈ 0.5
        assert forced[0] > cold[0]           # a forced drift raises the bar

    def test_single_axis_only_drifts_or_holds(self):
        d = _distribution(axes=("tone",))
        assert d[0] + d[1] == 1.0
        assert 0.23 <= d[0] <= 0.27          # holds ~25%
