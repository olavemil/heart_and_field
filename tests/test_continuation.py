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


# --- contextual bias (25.4b) ---------------------------------------------

from engine.continuation import CONTEXTUAL_GAIN, contextual_bias, prior_essence
from engine.event_taxonomy import EventDomain, EventNature, EventType
from engine.outcomes import OutcomeRecord, WeekPhase


def _et(domain, nature):
    return EventType(nature=nature, domain=domain)


class TestContextualBias:
    PRIOR = (EventDomain.RELATIONSHIP, EventNature.CONFRONTATION)

    def test_none_prior_is_neutral(self):
        et = _et(EventDomain.SPORT, EventNature.COLLABORATION)
        assert contextual_bias(et, prior=None, drifted=set()) == 1.0

    def test_hold_both_matching_is_full_boost(self):
        # Same essence, both axes held → both hit → 1 + gain.
        et = _et(EventDomain.RELATIONSHIP, EventNature.CONFRONTATION)
        assert contextual_bias(et, prior=self.PRIOR, drifted=set()) == 1.0 + CONTEXTUAL_GAIN

    def test_hold_both_but_different_is_no_boost(self):
        # Held axes that DON'T match the prior → no hits → 1.0.
        et = _et(EventDomain.SPORT, EventNature.INVITATION)
        assert contextual_bias(et, prior=self.PRIOR, drifted=set()) == 1.0

    def test_drift_axis_rewards_differing(self):
        # Drift nature: a candidate with a DIFFERENT nature (domain held)
        # hits both; one matching nature would miss the drift axis.
        drifted = {"nature"}
        differ = _et(EventDomain.RELATIONSHIP, EventNature.INVITATION)
        same = _et(EventDomain.RELATIONSHIP, EventNature.CONFRONTATION)
        assert contextual_bias(differ, prior=self.PRIOR, drifted=drifted) == 1.0 + CONTEXTUAL_GAIN
        # same nature: domain hit (held+match) but nature miss (drift+same)
        assert contextual_bias(same, prior=self.PRIOR, drifted=drifted) == 1.0 + CONTEXTUAL_GAIN / 2


class TestPriorEssence:
    def test_empty_log_is_none(self):
        assert prior_essence([]) is None

    def test_reads_most_recent_typed_outcome(self):
        log = [
            OutcomeRecord(
                event_id="a", timestamp=WeekPhase(1, 1), participants={},
                branch_taken="x", summary="s",
                taxonomy_id=_et(EventDomain.SPORT, EventNature.COLLABORATION),
            ),
            OutcomeRecord(
                event_id="b", timestamp=WeekPhase(1, 1), participants={},
                branch_taken="x", summary="s",
                taxonomy_id=_et(EventDomain.RELATIONSHIP, EventNature.ADMISSION),
            ),
        ]
        assert prior_essence(log) == (EventDomain.RELATIONSHIP, EventNature.ADMISSION)

    def test_skips_untyped_outcomes(self):
        log = [
            OutcomeRecord(
                event_id="a", timestamp=WeekPhase(1, 1), participants={},
                branch_taken="x", summary="s",
                taxonomy_id=_et(EventDomain.SECRET, EventNature.OBSERVATION),
            ),
            OutcomeRecord(  # no taxonomy_id (e.g. a match beat)
                event_id="b", timestamp=WeekPhase(1, 1), participants={},
                branch_taken="x", summary="s",
            ),
        ]
        assert prior_essence(log) == (EventDomain.SECRET, EventNature.OBSERVATION)
