"""Phase 11.5B: clock advance via events, enter_slot, and match flow."""

from pathlib import Path

import pytest

from engine.clock import Slot, Weekday, WorldClock
from engine.events import (
    BranchOutcome,
    EventBlueprint,
    RoleSlot,
    SceneBlock,
)
from engine.schedule import BlockType
from engine.session import GameSession


def _build_session() -> GameSession:
    return GameSession.new_game("Alex Morgan", seed=42)


def _basic_blueprint(
    duration_minutes: int = 60,
    branch_durations: dict[str, int] | None = None,
) -> EventBlueprint:
    branches = branch_durations or {}
    outcomes = {
        "default": BranchOutcome(
            summary="Something happened.",
            duration_minutes=branches.get("default"),
        )
    }
    for name, mins in branches.items():
        if name == "default":
            continue
        outcomes[name] = BranchOutcome(
            summary=f"{name} branch.",
            duration_minutes=mins,
        )
    return EventBlueprint(
        id=f"test.dur_{duration_minutes}_{'_'.join(sorted(branches))}",
        tags={"downtime"},
        participants=[RoleSlot(role="player")],
        blocks=[SceneBlock(id="main")],
        outcomes=outcomes,
        duration_minutes=duration_minutes,
    )


# --- Event durations advance the clock -------------------------------------


class TestEventDurationAdvancesClock:
    def test_blueprint_default_advances_one_hour(self):
        s = _build_session()
        s.start_week()
        before = s.state.clock.total_minutes_in_day()
        bp = _basic_blueprint(duration_minutes=60)
        s.schedule.slots[0].weekday = s.state.clock.weekday
        s.resolve_event(bp, "default", {}, slot_index=0)
        after = s.state.clock.total_minutes_in_day()
        assert after - before == 60

    def test_branch_override_takes_priority(self):
        s = _build_session()
        s.start_week()
        before = s.state.clock.total_minutes_in_day()
        bp = _basic_blueprint(
            duration_minutes=30,
            branch_durations={"long": 150},
        )
        s.resolve_event(bp, "long", {}, slot_index=0)
        after = s.state.clock.total_minutes_in_day()
        assert after - before == 150

    def test_game_phase_slot_does_not_advance_clock(self):
        s = _build_session()
        s.start_week()
        s.setup_match(opponent_count=11, opponent_name="Northgate")
        before_clock = s.state.clock.copy()
        # Pick the first GAME_PHASE slot.
        gp_idx = next(
            i for i, slot in enumerate(s.schedule.slots)
            if slot.block_type == BlockType.GAME_PHASE
        )
        bp = _basic_blueprint(duration_minutes=999)
        s.resolve_event(bp, "default", {}, slot_index=gp_idx)
        # Clock unchanged — match block consumes time as one chunk.
        assert s.state.clock == before_clock


# --- enter_slot fast-forward -----------------------------------------------


class TestEnterSlot:
    def test_advances_to_slot_anchor_same_day(self):
        s = _build_session()
        s.start_week()
        # Find Tuesday's training slot.
        tue_idx = next(
            i for i, slot in enumerate(s.schedule.slots)
            if slot.weekday == Weekday.TUE and slot.slot == Slot.MIDDAY
        )
        delta = s.enter_slot(tue_idx)
        # Mon 08:00 → Tue 12:00 = 1 day + 4 hours = 28 hours.
        assert delta == 28 * 60
        assert s.state.clock.weekday == Weekday.TUE
        assert s.state.clock.hour == 12
        assert s.state.clock.minute == 0

    def test_already_at_anchor_returns_zero(self):
        s = _build_session()
        s.start_week()
        # Mon morning slot — clock starts at Mon 08:00.
        mon_morning_idx = next(
            i for i, slot in enumerate(s.schedule.slots)
            if slot.weekday == Weekday.MON and slot.slot == Slot.MORNING
        )
        delta = s.enter_slot(mon_morning_idx)
        assert delta == 0
        assert s.state.clock.hour == 8

    def test_match_slot_lands_at_saturday_afternoon(self):
        s = _build_session()
        s.start_week()
        gp_idx = next(
            i for i, slot in enumerate(s.schedule.slots)
            if slot.block_type == BlockType.GAME_PHASE
        )
        s.enter_slot(gp_idx)
        assert s.state.clock.weekday == Weekday.SAT
        assert s.state.clock.hour == 16


# --- Match block -----------------------------------------------------------


class TestMatchBlock:
    def test_setup_sets_status_label(self):
        s = _build_session()
        s.start_week()
        s.setup_match(opponent_count=11, opponent_name="Northgate")
        d = s.clock_display()
        assert d.match_label == "Match vs Northgate"

    def test_evaluate_clears_label_and_advances_to_evening(self):
        s = _build_session()
        s.start_week()
        # Place clock at Saturday afternoon as if enter_slot ran.
        s.state.clock = WorldClock(
            week=1, weekday=Weekday.SAT, hour=16, minute=0,
        )
        s.setup_match(opponent_count=11, opponent_name="Northgate")
        # Run all 8 phases so evaluate has data.
        for phase in range(8):
            s.simulate_game_phase(phase, total_phases=8)
        s.evaluate_match()

        assert s._active_match_label is None
        assert s.state.clock.weekday == Weekday.SAT
        assert s.state.clock.hour == 20
        assert s.state.clock.minute == 0

    def test_no_match_results_still_clears_label(self):
        s = _build_session()
        s.start_week()
        s.setup_match(opponent_count=11, opponent_name="Northgate")
        # No phases simulated — evaluate_match should still clean up.
        s.evaluate_match()
        assert s._active_match_label is None


# --- Schedule generate covers full calendar --------------------------------


class TestGeneratedCalendar:
    def test_default_slots_have_weekday_and_slot(self):
        s = _build_session()
        sched = s.start_week()
        for slot in sched.slots:
            assert slot.weekday is not None
            assert slot.slot is not None

    def test_match_phases_on_saturday_afternoon(self):
        s = _build_session()
        sched = s.start_week()
        gp_slots = [s for s in sched.slots if s.block_type == BlockType.GAME_PHASE]
        assert len(gp_slots) == 8
        for s_ in gp_slots:
            assert s_.weekday == Weekday.SAT
            assert s_.slot == Slot.AFTERNOON

    def test_postgame_on_saturday_evening(self):
        s = _build_session()
        sched = s.start_week()
        postgame = next(
            s_ for s_ in sched.slots if s_.block_type == BlockType.POSTGAME
        )
        assert postgame.weekday == Weekday.SAT
        assert postgame.slot == Slot.EVENING
