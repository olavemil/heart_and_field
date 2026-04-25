"""Tests for the colour-grade pipeline (engine.color_grades)."""

import json
import random
from pathlib import Path

import pytest

from engine.color_grades import (
    MOOD_GRADES,
    SceneAtmosphere,
    SceneMood,
    TIME_OF_DAY_GRADES,
    TimeOfDay,
    WEATHER_GRADES,
    WEATHER_NEIGHBORS,
    Weather,
    _all_grades,
    _hex_to_rgb,
    _table_hash,
    derive_mood,
    draw_weather,
    draw_weather_tendency,
    generate_grade_pngs,
    grade_path,
    time_of_day_for_hour,
)


# --- Lookup tables ---------------------------------------------------------


class TestLookupTables:
    def test_every_time_of_day_has_grade(self):
        for tod in TimeOfDay:
            assert tod in TIME_OF_DAY_GRADES

    def test_every_weather_has_grade(self):
        for w in Weather:
            assert w in WEATHER_GRADES

    def test_every_mood_has_grade(self):
        for m in SceneMood:
            assert m in MOOD_GRADES



# --- Mood derivation -------------------------------------------------------


class TestDeriveMood:
    def test_neutral_on_neutral_state(self):
        assert derive_mood(0.0, 0.0) == SceneMood.NEUTRAL

    def test_euphoric_high_morale_and_momentum(self):
        assert derive_mood(0.6, 0.5) == SceneMood.EUPHORIC

    def test_melancholy_dominates_over_charged(self):
        # A bruising loss with whip-back momentum still reads as melancholy —
        # the dominant emotional truth wins.
        assert derive_mood(-0.7, 0.8) == SceneMood.MELANCHOLY

    def test_charged_on_big_momentum_swing_no_morale_loss(self):
        assert derive_mood(0.0, 0.7) == SceneMood.CHARGED
        assert derive_mood(0.0, -0.7) == SceneMood.CHARGED

    def test_tense_on_mild_negative_morale(self):
        assert derive_mood(-0.2, 0.0) == SceneMood.TENSE

    def test_euphoric_requires_both_morale_and_momentum(self):
        # High morale alone isn't euphoric — momentum is the kicker.
        assert derive_mood(0.6, 0.0) == SceneMood.NEUTRAL


# --- Time-of-day mapping ---------------------------------------------------


class TestTimeOfDayMapping:
    def test_morning_hour_reads_morning(self):
        assert time_of_day_for_hour(8) == TimeOfDay.MORNING
        assert time_of_day_for_hour(10) == TimeOfDay.MORNING

    def test_midday_hour_reads_midday(self):
        assert time_of_day_for_hour(12) == TimeOfDay.MIDDAY
        assert time_of_day_for_hour(14) == TimeOfDay.MIDDAY

    def test_afternoon_hour_reads_afternoon(self):
        assert time_of_day_for_hour(16) == TimeOfDay.AFTERNOON
        assert time_of_day_for_hour(18) == TimeOfDay.AFTERNOON

    def test_evening_hour_reads_evening(self):
        assert time_of_day_for_hour(20) == TimeOfDay.EVENING
        assert time_of_day_for_hour(21) == TimeOfDay.EVENING

    def test_late_night_reads_night(self):
        assert time_of_day_for_hour(23) == TimeOfDay.NIGHT
        assert time_of_day_for_hour(2) == TimeOfDay.NIGHT

    def test_dawn_reads_dawn(self):
        assert time_of_day_for_hour(5) == TimeOfDay.DAWN
        assert time_of_day_for_hour(6) == TimeOfDay.DAWN

    def test_hour_wraps_modulo_24(self):
        assert time_of_day_for_hour(36) == time_of_day_for_hour(12)


# --- Weather draws ---------------------------------------------------------


class TestWeatherDraws:
    def test_tendency_uniform_over_three_values(self):
        rng = random.Random(0)
        counts = {w: 0 for w in Weather}
        for _ in range(1500):
            counts[draw_weather_tendency(rng)] += 1
        # Uniform-ish over three buckets.
        for w in Weather:
            assert 350 < counts[w] < 650

    def test_draw_weather_biased_toward_tendency(self):
        rng = random.Random(1)
        counts = {w: 0 for w in Weather}
        for _ in range(2000):
            counts[draw_weather(Weather.RAIN, rng)] += 1
        # ~70% rain, ~30% to OVERCAST (RAIN's only neighbor).
        assert counts[Weather.RAIN] > 1300
        assert counts[Weather.OVERCAST] > 300
        # RAIN ↔ CLEAR is intentionally not adjacent — no jumpy weather.
        assert counts[Weather.CLEAR] == 0

    def test_neighbor_table_symmetric_for_overcast(self):
        # OVERCAST is the bridge between CLEAR and RAIN; both list it
        # as a neighbor.
        assert Weather.OVERCAST in WEATHER_NEIGHBORS[Weather.CLEAR]
        assert Weather.OVERCAST in WEATHER_NEIGHBORS[Weather.RAIN]


# --- PNG generation + cache ------------------------------------------------


class TestGeneratePngs:
    def test_generates_one_png_per_grade(self, tmp_path: Path):
        paths = generate_grade_pngs(tmp_path)
        expected_count = (
            len(TIME_OF_DAY_GRADES)
            + len(WEATHER_GRADES)
            + len(MOOD_GRADES)
        )
        assert len(paths) == expected_count
        for p in paths.values():
            assert p.exists()
            assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_writes_index_with_hash(self, tmp_path: Path):
        generate_grade_pngs(tmp_path)
        index = json.loads((tmp_path / "_index.json").read_text())
        assert index["hash"] == _table_hash()

    def test_cache_skips_when_hash_matches(self, tmp_path: Path):
        paths = generate_grade_pngs(tmp_path)
        # Stamp the files so we can detect rewrites.
        before = {p: p.stat().st_mtime_ns for p in paths.values()}

        # Second call with no table change must not rewrite.
        generate_grade_pngs(tmp_path)
        after = {p: p.stat().st_mtime_ns for p in paths.values()}
        assert before == after

    def test_cache_regenerates_on_missing_file(self, tmp_path: Path):
        paths = generate_grade_pngs(tmp_path)
        # User deletes one PNG — next call must restore it without
        # waiting for a hash change.
        victim = next(iter(paths.values()))
        victim.unlink()
        generate_grade_pngs(tmp_path)
        assert victim.exists()

    def test_cache_regenerates_on_index_corruption(self, tmp_path: Path):
        generate_grade_pngs(tmp_path)
        (tmp_path / "_index.json").write_text("not json")
        # Should regenerate without raising.
        generate_grade_pngs(tmp_path)
        assert (tmp_path / "_index.json").exists()
        assert json.loads((tmp_path / "_index.json").read_text())["hash"]

    def test_grade_path_round_trips(self, tmp_path: Path):
        generate_grade_pngs(tmp_path)
        path = grade_path(tmp_path, "time", TimeOfDay.DAWN.value)
        assert path.exists()


class TestPngContent:
    def test_pixel_colour_matches_table(self, tmp_path: Path):
        from PIL import Image

        generate_grade_pngs(tmp_path)
        path = grade_path(tmp_path, "time", TimeOfDay.NIGHT.value)
        img = Image.open(path).convert("RGB")
        sample = img.getpixel((0, 0))
        expected = _hex_to_rgb(TIME_OF_DAY_GRADES[TimeOfDay.NIGHT].tint)
        assert sample == expected


# --- Hash invariance -------------------------------------------------------


class TestTableHash:
    def test_hash_stable_across_runs(self):
        assert _table_hash() == _table_hash()

    def test_hash_changes_with_table_edit(self, monkeypatch):
        monkeypatch.setitem(
            TIME_OF_DAY_GRADES,
            TimeOfDay.NIGHT,
            TIME_OF_DAY_GRADES[TimeOfDay.NIGHT].__class__(
                "000000", 0.5, 1.0, 1.0
            ),
        )
        # The monkeypatch swap must produce a different hash.
        assert _table_hash() != _baseline_hash()


# Captured at import time so monkeypatch tests can compare against it.
def _baseline_hash() -> str:
    # Use the same payload formula as _table_hash but built from a cached
    # snapshot. Simpler: compute once now and stash.
    return _BASELINE


_BASELINE = _table_hash()


# --- SceneAtmosphere -------------------------------------------------------


class TestSceneAtmosphere:
    def test_constructible(self):
        atm = SceneAtmosphere(
            time_of_day=TimeOfDay.MIDDAY,
            weather=Weather.CLEAR,
            mood=SceneMood.NEUTRAL,
            weather_tendency=Weather.CLEAR,
        )
        assert atm.time_of_day == TimeOfDay.MIDDAY
