"""Integration: GameSession ↔ overlay pipeline (Phase 11C)."""

from pathlib import Path

import pytest

from engine.background_generator import NoOpPrefetchScheduler
from engine.background_pool import LocationDescriptor, LocationKind
from engine.clock import Weekday, WorldClock
from engine.color_grades import Weather
from engine.overlays import NoiseOverlay
from engine.session import GameSession


def _build_session(tmp_path: Path) -> GameSession:
    s = GameSession.new_game("Alex Morgan", seed=42)
    s.init_backgrounds(
        tmp_path / "bg",
        prefetch_scheduler=NoOpPrefetchScheduler(),
    )
    return s


class TestInit:
    def test_init_backgrounds_generates_overlays(self, tmp_path: Path):
        s = _build_session(tmp_path)
        assert s.overlays_root is not None
        # Every authored overlay PNG must be present after init.
        for overlay in NoiseOverlay:
            from engine.overlays import OVERLAY_SPECS
            path = s.overlays_root / OVERLAY_SPECS[overlay].path
            assert path.exists()


class TestOverlaysForScene:
    def test_returns_empty_when_pipeline_off(self, tmp_path: Path):
        s = GameSession.new_game("Alex Morgan", seed=42)
        # No init_backgrounds called.
        assert s.overlays_for_scene("any", "any") == []

    def test_returns_empty_for_unknown_graph(self, tmp_path: Path):
        s = _build_session(tmp_path)
        assert s.overlays_for_scene("nope", "front_door") == []

    def test_house_overlays_have_grain_and_dust(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.background_manifest.create_graph(
            "suburban_house",
            LocationDescriptor(kind=LocationKind.SUBURBAN_HOUSE),
            graph_id="g1",
        )
        result = s.overlays_for_scene("g1", "front_door")
        overlays = {spec.overlay for spec, _ in result}
        assert NoiseOverlay.FILM_GRAIN in overlays
        assert NoiseOverlay.LIGHT_DUST in overlays

    def test_returned_paths_resolve_under_overlays_root(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.background_manifest.create_graph(
            "suburban_house",
            LocationDescriptor(kind=LocationKind.SUBURBAN_HOUSE),
            graph_id="g1",
        )
        result = s.overlays_for_scene("g1", "front_door")
        for _, path in result:
            assert path.exists()
            assert path.is_relative_to(s.overlays_root)

    def test_rain_weather_adds_streak_overlay(self, tmp_path: Path):
        s = _build_session(tmp_path)
        sched = s.start_week()
        # Force the Monday weather to RAIN.
        sched.daily_weathers["mon"] = Weather.RAIN.value
        s.background_manifest.create_graph(
            "suburban_house",
            LocationDescriptor(kind=LocationKind.SUBURBAN_HOUSE),
            graph_id="g1",
        )
        result = s.overlays_for_scene("g1", "front_door")
        overlays = {spec.overlay for spec, _ in result}
        assert NoiseOverlay.RAIN_STREAK in overlays
