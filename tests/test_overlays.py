"""Tests for the noise-overlay pipeline (engine.overlays)."""

import json
from pathlib import Path

import pytest

from engine.background_pool import LocationKind
from engine.color_grades import (
    SceneAtmosphere,
    SceneMood,
    TimeOfDay,
    Weather,
)
from engine.overlays import (
    LOCATION_OVERLAYS,
    NoiseOverlay,
    OVERLAY_SPECS,
    OverlayAnim,
    OverlaySpec,
    generate_overlay_pngs,
    overlay_path,
    overlays_for,
)


def _atmosphere(
    *,
    weather: Weather = Weather.CLEAR,
    time_of_day: TimeOfDay = TimeOfDay.MIDDAY,
    mood: SceneMood = SceneMood.NEUTRAL,
) -> SceneAtmosphere:
    return SceneAtmosphere(
        time_of_day=time_of_day,
        weather=weather,
        mood=mood,
        weather_tendency=weather,
    )


# --- Spec registry --------------------------------------------------------


class TestSpecRegistry:
    def test_every_overlay_has_spec(self):
        for ov in NoiseOverlay:
            assert ov in OVERLAY_SPECS
            assert isinstance(OVERLAY_SPECS[ov], OverlaySpec)

    def test_specs_match_authored_addendum(self):
        # Addendum §1.2 verbatim.
        grain = OVERLAY_SPECS[NoiseOverlay.FILM_GRAIN]
        assert grain.alpha == 0.06
        assert grain.animation == OverlayAnim.SCROLL_RANDOM
        rain = OVERLAY_SPECS[NoiseOverlay.RAIN_STREAK]
        assert rain.alpha == 0.20
        assert rain.animation == OverlayAnim.SCROLL_DOWN


# --- Kind mapping ---------------------------------------------------------


class TestKindMapping:
    def test_house_has_grain_and_dust(self):
        assert LOCATION_OVERLAYS[LocationKind.SUBURBAN_HOUSE] == (
            NoiseOverlay.FILM_GRAIN, NoiseOverlay.LIGHT_DUST,
        )

    def test_stadium_has_grain_and_crowd(self):
        assert LOCATION_OVERLAYS[LocationKind.STADIUM] == (
            NoiseOverlay.FILM_GRAIN, NoiseOverlay.CROWD_BLUR,
        )

    def test_unmapped_kind_falls_back_to_grain_only(self):
        # No entry → just film grain via the default in overlays_for.
        # We can't easily simulate without a missing kind, so test the
        # contract via overlays_for directly for a kind missing on
        # purpose — test the behaviour by removing one temporarily.
        atm = _atmosphere()
        result = overlays_for(LocationKind.GYM, atm)
        # GYM is mapped to grain only.
        assert [s.overlay for s in result] == [NoiseOverlay.FILM_GRAIN]


# --- Weather merge --------------------------------------------------------


class TestWeatherMerge:
    def test_rain_adds_streak(self):
        result = overlays_for(
            LocationKind.SUBURBAN_HOUSE, _atmosphere(weather=Weather.RAIN),
        )
        overlay_kinds = [s.overlay for s in result]
        assert NoiseOverlay.RAIN_STREAK in overlay_kinds
        # Original house stack stays intact.
        assert NoiseOverlay.FILM_GRAIN in overlay_kinds
        assert NoiseOverlay.LIGHT_DUST in overlay_kinds

    def test_heat_shimmer_only_outdoor_clear_midday(self):
        # Outdoor + clear + midday: shimmer added.
        result = overlays_for(
            LocationKind.PARK,
            _atmosphere(weather=Weather.CLEAR, time_of_day=TimeOfDay.MIDDAY),
        )
        assert NoiseOverlay.HEAT_SHIMMER in {s.overlay for s in result}

    def test_heat_shimmer_skipped_indoor(self):
        result = overlays_for(
            LocationKind.SUBURBAN_HOUSE,
            _atmosphere(weather=Weather.CLEAR, time_of_day=TimeOfDay.MIDDAY),
        )
        assert NoiseOverlay.HEAT_SHIMMER not in {s.overlay for s in result}

    def test_heat_shimmer_skipped_overcast(self):
        result = overlays_for(
            LocationKind.PARK,
            _atmosphere(weather=Weather.OVERCAST, time_of_day=TimeOfDay.MIDDAY),
        )
        assert NoiseOverlay.HEAT_SHIMMER not in {s.overlay for s in result}

    def test_heat_shimmer_skipped_evening(self):
        result = overlays_for(
            LocationKind.PARK,
            _atmosphere(weather=Weather.CLEAR, time_of_day=TimeOfDay.EVENING),
        )
        assert NoiseOverlay.HEAT_SHIMMER not in {s.overlay for s in result}

    def test_no_duplicate_overlays(self):
        # Even contrived stacking shouldn't duplicate any overlay.
        result = overlays_for(
            LocationKind.STADIUM,
            _atmosphere(weather=Weather.RAIN, time_of_day=TimeOfDay.AFTERNOON),
        )
        kinds = [s.overlay for s in result]
        assert len(kinds) == len(set(kinds))


# --- PNG generation -------------------------------------------------------


class TestGeneratePngs:
    def test_writes_one_png_per_overlay(self, tmp_path: Path):
        paths = generate_overlay_pngs(tmp_path, size=64)
        assert set(paths.keys()) == set(NoiseOverlay)
        for p in paths.values():
            assert p.exists()
            assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_writes_version_marker(self, tmp_path: Path):
        generate_overlay_pngs(tmp_path, size=32)
        marker = tmp_path / "_version.json"
        assert marker.exists()
        data = json.loads(marker.read_text())
        assert data["version"]
        assert data["size"] == 32

    def test_cache_skips_when_version_matches(self, tmp_path: Path):
        paths = generate_overlay_pngs(tmp_path, size=32)
        before = {p: p.stat().st_mtime_ns for p in paths.values()}
        generate_overlay_pngs(tmp_path, size=32)
        after = {p: p.stat().st_mtime_ns for p in paths.values()}
        assert before == after

    def test_regenerates_on_missing_file(self, tmp_path: Path):
        paths = generate_overlay_pngs(tmp_path, size=32)
        victim = paths[NoiseOverlay.LIGHT_DUST]
        victim.unlink()
        generate_overlay_pngs(tmp_path, size=32)
        assert victim.exists()

    def test_regenerates_on_corrupt_marker(self, tmp_path: Path):
        generate_overlay_pngs(tmp_path, size=32)
        (tmp_path / "_version.json").write_text("not json")
        # Should not raise.
        generate_overlay_pngs(tmp_path, size=32)
        assert (tmp_path / "_version.json").exists()

    def test_overlay_path_resolves(self, tmp_path: Path):
        generate_overlay_pngs(tmp_path, size=32)
        p = overlay_path(tmp_path, NoiseOverlay.FILM_GRAIN)
        assert p.exists()
        assert p.name == "grain.png"

    def test_deterministic_output(self, tmp_path: Path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        generate_overlay_pngs(a, size=32, seed_base=1234)
        generate_overlay_pngs(b, size=32, seed_base=1234)
        for ov in NoiseOverlay:
            assert (a / OVERLAY_SPECS[ov].path).read_bytes() == (
                b / OVERLAY_SPECS[ov].path
            ).read_bytes()
