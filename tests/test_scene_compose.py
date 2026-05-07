"""Tests for the scene-composition crossfade math (engine.scene_compose)."""

import pytest

from engine.scene_compose import variant_crossfade_state


# --- Single-variant short-circuit -----------------------------------------


class TestSingleVariant:
    def test_zero_variants_returns_zeros(self):
        assert variant_crossfade_state(0.0, 0) == (0, 0, 0.0)

    def test_one_variant_returns_zeros(self):
        # No crossfade with a single variant — renderer shows it static.
        assert variant_crossfade_state(0.0, 1) == (0, 0, 0.0)
        assert variant_crossfade_state(5.0, 1) == (0, 0, 0.0)
        assert variant_crossfade_state(100.0, 1) == (0, 0, 0.0)


# --- Two-variant cycle -----------------------------------------------------


class TestTwoVariants:
    def test_t_zero_starts_a_to_b(self):
        idx_a, idx_b, progress = variant_crossfade_state(0.0, 2)
        assert (idx_a, idx_b) == (0, 1)
        assert progress == 0.0

    def test_half_through_first_fade(self):
        idx_a, idx_b, progress = variant_crossfade_state(0.5, 2)
        assert (idx_a, idx_b) == (0, 1)
        assert progress == pytest.approx(0.5)

    def test_just_before_first_completion(self):
        idx_a, idx_b, progress = variant_crossfade_state(0.999, 2)
        assert (idx_a, idx_b) == (0, 1)
        assert progress == pytest.approx(0.999)

    def test_one_second_in_swaps_to_b_to_a(self):
        idx_a, idx_b, progress = variant_crossfade_state(1.0, 2)
        assert (idx_a, idx_b) == (1, 0)
        assert progress == 0.0

    def test_full_cycle_wraps(self):
        # 2 variants × 1s = 2s loop period.
        idx_a, idx_b, progress = variant_crossfade_state(2.0, 2)
        assert (idx_a, idx_b) == (0, 1)
        assert progress == 0.0

    def test_continuous_no_hold(self):
        # Sample 0.0 through 2.0 and verify progress moves forward
        # smoothly, never holds at 0 or 1 (apart from the boundary).
        prev_state = None
        for i in range(1, 20):
            t = i * 0.1
            state = variant_crossfade_state(t, 2)
            # Progress is always strictly between 0 and 1 except at the
            # boundary, and the (a,b) pair is consistent.
            assert 0.0 <= state[2] < 1.0
            if prev_state is not None and prev_state[:2] == state[:2]:
                # Within the same A→B segment, progress monotonic.
                assert state[2] >= prev_state[2]
            prev_state = state


# --- Three-variant cycle ---------------------------------------------------


class TestThreeVariants:
    def test_progresses_through_all_three(self):
        # 3 variants × 1s = 3s loop period.
        ab = variant_crossfade_state(0.5, 3)
        bc = variant_crossfade_state(1.5, 3)
        ca = variant_crossfade_state(2.5, 3)
        assert ab[:2] == (0, 1)
        assert bc[:2] == (1, 2)
        assert ca[:2] == (2, 0)

    def test_full_cycle_wraps(self):
        idx_a, idx_b, progress = variant_crossfade_state(3.0, 3)
        assert (idx_a, idx_b) == (0, 1)
        assert progress == 0.0


# --- Custom fade duration --------------------------------------------------


class TestCustomFade:
    def test_two_second_fade(self):
        # With fade_seconds=2.0, A→B completes at t=2.
        idx_a, idx_b, progress = variant_crossfade_state(1.0, 2, 2.0)
        assert (idx_a, idx_b) == (0, 1)
        assert progress == pytest.approx(0.5)

    def test_invalid_fade_rejected(self):
        with pytest.raises(ValueError):
            variant_crossfade_state(0.0, 2, 0.0)
        with pytest.raises(ValueError):
            variant_crossfade_state(0.0, 2, -1.0)


# --- Robustness ------------------------------------------------------------


class TestRobustness:
    def test_negative_shown_time_clamps(self):
        # Some Ren'Py paths can briefly hand a negative shown_time
        # during a scene transition; we clamp rather than raise.
        idx_a, idx_b, progress = variant_crossfade_state(-0.5, 2)
        assert (idx_a, idx_b) == (0, 1)
        assert progress == 0.0

    def test_very_large_shown_time_wraps(self):
        idx_a, idx_b, progress = variant_crossfade_state(10_000.5, 2)
        # 10000.5 / 1.0 = 10000.5 → 10000.5 % 2 = 0.5 → idx_a=0, idx_b=1
        assert (idx_a, idx_b) == (0, 1)
        assert progress == pytest.approx(0.5)
