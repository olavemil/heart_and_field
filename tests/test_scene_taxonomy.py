"""Tests for the scene taxonomy (engine.scene_taxonomy, Phase 16)."""

import pytest

from engine.background_pool import LocationKind
from engine.scene_taxonomy import (
    SCENE_ADJACENCY,
    SCENE_CATEGORY,
    SCENE_INSTANCE_TYPE,
    SceneCategory,
    SceneInstance,
    SceneType,
    category_for_scene_type,
    instances_of,
    location_kind_for_scene_type,
    neighbors,
    scene_type_for_instance,
    scene_type_for_location_kind,
)


# --- Enum coverage --------------------------------------------------------


class TestEnumCoverage:
    def test_every_scene_type_has_category(self):
        for st in SceneType:
            assert st in SCENE_CATEGORY
            assert isinstance(SCENE_CATEGORY[st], SceneCategory)

    def test_every_instance_has_parent_type(self):
        for inst in SceneInstance:
            assert inst in SCENE_INSTANCE_TYPE
            assert isinstance(SCENE_INSTANCE_TYPE[inst], SceneType)

    def test_category_for_scene_type_helper(self):
        assert category_for_scene_type(SceneType.LOCKER_ROOM) == SceneCategory.SPORT
        assert category_for_scene_type(SceneType.BAR) == SceneCategory.SOCIAL
        assert category_for_scene_type(SceneType.HOTEL_ROOM) == SceneCategory.PRIVATE
        assert category_for_scene_type(SceneType.PLANE) == SceneCategory.TRANSIT
        assert category_for_scene_type(SceneType.STUDIO) == SceneCategory.MEDIA
        assert category_for_scene_type(SceneType.COURTROOM) == SceneCategory.INSTITUTIONAL


# --- Scene instance ↔ scene type ------------------------------------------


class TestSceneInstance:
    def test_apartment_instances_map_to_apartment_type(self):
        for inst in (SceneInstance.APARTMENT_SHARED, SceneInstance.APARTMENT_SOLO,
                     SceneInstance.APARTMENT_UPSCALE):
            assert scene_type_for_instance(inst) == SceneType.APARTMENT

    def test_bar_instances_map_to_bar_type(self):
        for inst in (SceneInstance.BAR_LOCAL, SceneInstance.BAR_UPSCALE):
            assert scene_type_for_instance(inst) == SceneType.BAR

    def test_instances_of_apartment(self):
        out = instances_of(SceneType.APARTMENT)
        assert set(out) == {
            SceneInstance.APARTMENT_SHARED,
            SceneInstance.APARTMENT_SOLO,
            SceneInstance.APARTMENT_UPSCALE,
        }

    def test_instances_of_isolated_type_returns_empty(self):
        # PRESS_ROOM has no authored instances yet.
        assert instances_of(SceneType.PRESS_ROOM) == []


# --- Scene adjacency graph -----------------------------------------------


class TestSceneAdjacency:
    def test_adjacency_is_undirected(self):
        # Every edge appears in both directions.
        for src, dsts in SCENE_ADJACENCY.items():
            for dst in dsts:
                assert src in SCENE_ADJACENCY[dst], (
                    f"{src} → {dst} edge missing reverse"
                )

    def test_authored_edges_present(self):
        # Spot-check a few from addendum §4.2.
        assert SceneType.TUNNEL in neighbors(SceneType.LOCKER_ROOM)
        assert SceneType.LOCKER_ROOM in neighbors(SceneType.TUNNEL)
        assert SceneType.HOTEL_ROOM in neighbors(SceneType.BAR)
        assert SceneType.AIRPORT in neighbors(SceneType.PLANE)

    def test_isolated_type_has_empty_neighbours(self):
        # PRESS_ROOM, COURTROOM not authored into the graph yet.
        assert neighbors(SceneType.PRESS_ROOM) == frozenset()
        assert neighbors(SceneType.COURTROOM) == frozenset()

    def test_neighbors_returns_frozenset(self):
        # Immutable, safe to share without aliasing concerns.
        assert isinstance(neighbors(SceneType.BAR), frozenset)


# --- LocationKind bridge --------------------------------------------------


class TestBridge:
    def test_every_location_kind_has_a_scene_type(self):
        for kind in LocationKind:
            assert scene_type_for_location_kind(kind) is not None

    def test_house_kind_maps_to_house_type(self):
        assert scene_type_for_location_kind(LocationKind.SUBURBAN_HOUSE) == SceneType.HOUSE

    def test_stadium_kind_maps_to_pitch_type(self):
        assert scene_type_for_location_kind(LocationKind.STADIUM) == SceneType.PITCH

    def test_house_type_routes_back_to_suburban_house_kind(self):
        # Round-trip through the bridge.
        st = scene_type_for_location_kind(LocationKind.SUBURBAN_HOUSE)
        back = location_kind_for_scene_type(st)
        assert back == LocationKind.SUBURBAN_HOUSE

    def test_transit_types_have_no_visual_kind(self):
        # Transit isn't yet wired into the visual pipeline; the reverse
        # bridge returns None so callers can decide to skip generation.
        assert location_kind_for_scene_type(SceneType.PLANE) is None
        assert location_kind_for_scene_type(SceneType.BUS) is None
        assert location_kind_for_scene_type(SceneType.STATION) is None

    def test_press_room_falls_through_to_school_visually(self):
        # No bespoke visual yet — institutional / media types fall
        # through to the school visual placeholder.
        assert location_kind_for_scene_type(SceneType.PRESS_ROOM) == LocationKind.SCHOOL
        assert location_kind_for_scene_type(SceneType.COURTROOM) == LocationKind.SCHOOL
