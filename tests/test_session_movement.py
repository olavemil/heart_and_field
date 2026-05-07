"""Phase 11.5C: movement costs (resolve_scene → clock advance)."""

from pathlib import Path

import pytest

from engine.background_generator import NoOpPrefetchScheduler
from engine.background_pool import LocationKind
from engine.clock import Slot, Weekday, WorldClock
from engine.events import (
    BranchOutcome,
    EventBlueprint,
    LocationCue,
    RoleSlot,
    SceneBlock,
)
from engine.session import GameSession


def _build_session(tmp_path: Path) -> GameSession:
    s = GameSession.new_game("Alex Morgan", seed=42)
    s.init_backgrounds(
        tmp_path / "bg",
        prefetch_scheduler=NoOpPrefetchScheduler(),
    )
    return s


def _bp(
    *,
    spec_id: str = "suburban_house",
    node: str = "front_door",
    graph_id: str | None = None,
    suffix: str = "x",
) -> EventBlueprint:
    return EventBlueprint(
        id=f"test.move_{suffix}",
        tags={"downtime"},
        participants=[RoleSlot(role="player")],
        blocks=[SceneBlock(id="main")],
        outcomes={"default": BranchOutcome(summary=".")},
        location=LocationCue(
            spec_id=spec_id,
            node_name=node,
            graph_id=graph_id,
        ),
    )


# --- First-time arrival is free -------------------------------------------


class TestFirstArrival:
    def test_no_cost_when_current_location_none(self, tmp_path: Path):
        s = _build_session(tmp_path)
        before = s.state.clock.copy()
        s.resolve_scene(_bp(graph_id="player_home"), {})
        assert s.state.clock == before
        assert s.state.current_location == ("player_home", "front_door")


# --- Cost matrix -----------------------------------------------------------


class TestCostMatrix:
    def test_revisit_same_node_zero(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.resolve_scene(_bp(graph_id="player_home"), {})
        before = s.state.clock.total_minutes_in_day()
        s.resolve_scene(_bp(graph_id="player_home"), {})
        assert s.state.clock.total_minutes_in_day() - before == 0

    def test_same_graph_different_node_five_min(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.resolve_scene(_bp(graph_id="player_home", node="front_door"), {})
        before = s.state.clock.total_minutes_in_day()
        s.resolve_scene(_bp(graph_id="player_home", node="kitchen"), {})
        assert s.state.clock.total_minutes_in_day() - before == 5

    def test_different_graph_thirty_min(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.resolve_scene(_bp(graph_id="player_home", node="front_door"), {})
        before = s.state.clock.total_minutes_in_day()
        s.resolve_scene(
            _bp(spec_id="school", node="locker_bay", graph_id="main_school"),
            {},
        )
        assert s.state.clock.total_minutes_in_day() - before == 30


# --- Auto-teleport at slot anchors ----------------------------------------


class TestSlotTeleport:
    def test_enter_slot_grants_free_first_arrival(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.start_week()

        # Establish a location at home.
        s.resolve_scene(_bp(graph_id="player_home"), {})
        # Now jump to Tuesday training slot — under normal cost it would
        # be 30 min (different graph), but enter_slot grants free arrival.
        tue_idx = next(
            i for i, slot in enumerate(s.schedule.slots)
            if slot.weekday == Weekday.TUE and slot.slot == Slot.MIDDAY
        )
        s.enter_slot(tue_idx)
        before = s.state.clock.total_minutes_in_day()
        s.resolve_scene(
            _bp(spec_id="school", node="locker_bay", graph_id="main_school"),
            {},
        )
        # No movement cost added on top of the slot fast-forward.
        assert s.state.clock.total_minutes_in_day() == before

    def test_teleport_consumed_by_first_resolve_scene(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.start_week()

        s.resolve_scene(_bp(graph_id="player_home"), {})
        tue_idx = next(
            i for i, slot in enumerate(s.schedule.slots)
            if slot.weekday == Weekday.TUE and slot.slot == Slot.MIDDAY
        )
        s.enter_slot(tue_idx)

        # First resolve_scene: free.
        s.resolve_scene(
            _bp(spec_id="school", node="locker_bay", graph_id="main_school"),
            {},
        )
        # Second resolve_scene in the same slot: pays the normal cost.
        before = s.state.clock.total_minutes_in_day()
        s.resolve_scene(_bp(graph_id="player_home"), {})
        assert s.state.clock.total_minutes_in_day() - before == 30


# --- current_location persistence -----------------------------------------


class TestCurrentLocationPersistence:
    def test_save_round_trip(self, tmp_path: Path):
        from engine.save import deserialise, serialise

        s = _build_session(tmp_path)
        s.resolve_scene(_bp(graph_id="player_home", node="kitchen"), {})
        assert s.state.current_location == ("player_home", "kitchen")
        data = serialise(s.state)
        restored, _, _ = deserialise(data)
        assert restored.current_location == ("player_home", "kitchen")

    def test_save_handles_none_location(self, tmp_path: Path):
        from engine.save import deserialise, serialise

        s = _build_session(tmp_path)
        # No resolve_scene called.
        data = serialise(s.state)
        restored, _, _ = deserialise(data)
        assert restored.current_location is None
