"""Integration: GameSession ↔ colour-grade pipeline (Phase 11B + 11.5A)."""

from pathlib import Path

import pytest

from engine.background_generator import NoOpPrefetchScheduler
from engine.clock import Slot, Weekday, WorldClock
from engine.color_grades import (
    SceneMood,
    TimeOfDay,
    Weather,
)
from engine.schedule import BlockType
from engine.session import GameSession


def _build_session(tmp_path: Path) -> GameSession:
    s = GameSession.new_game("Alex Morgan", seed=42)
    s.init_backgrounds(
        tmp_path / "bg",
        prefetch_scheduler=NoOpPrefetchScheduler(),
    )
    return s


# --- Schedule weather draws ------------------------------------------------


class TestStartWeekDrawsWeather:
    def test_tendency_set_after_start_week(self, tmp_path: Path):
        s = _build_session(tmp_path)
        sched = s.start_week()
        assert sched.weather_tendency in {w.value for w in Weather}

    def test_one_weather_per_active_weekday(self, tmp_path: Path):
        s = _build_session(tmp_path)
        sched = s.start_week()
        active_weekdays = {
            slot.weekday.value
            for slot in sched.slots
            if slot.weekday is not None
        }
        assert set(sched.daily_weathers.keys()) == active_weekdays

    def test_match_day_slots_share_weather(self, tmp_path: Path):
        s = _build_session(tmp_path)
        sched = s.start_week()
        # All eight game-phase slots are on Saturday and read the same
        # daily draw.
        sat_value = sched.daily_weathers["sat"]
        for slot in sched.slots:
            if slot.block_type == BlockType.GAME_PHASE:
                assert slot.weekday.value == "sat"
                assert sched.weather_for(slot.weekday) == sat_value

    def test_start_week_resets_clock_to_monday_morning(self, tmp_path: Path):
        s = _build_session(tmp_path)
        # Mutate clock first, then verify start_week resets it.
        s.state.clock.advance(180)
        s.start_week()
        assert s.state.clock.weekday == Weekday.MON
        assert s.state.clock.hour == 8
        assert s.state.clock.minute == 0


# --- atmosphere() ---------------------------------------------------------


class TestAtmosphere:
    def test_pre_start_week_uses_clock_default(self, tmp_path: Path):
        s = _build_session(tmp_path)
        # Default clock is Monday 08:00 → MORNING.
        atm = s.atmosphere()
        assert atm.time_of_day == TimeOfDay.MORNING
        assert atm.weather == Weather.CLEAR
        assert atm.mood == SceneMood.NEUTRAL

    def test_time_of_day_follows_clock_hour(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.start_week()
        s.state.clock = WorldClock(week=1, weekday=Weekday.MON, hour=20, minute=0)
        assert s.atmosphere().time_of_day == TimeOfDay.EVENING
        s.state.clock = WorldClock(week=1, weekday=Weekday.MON, hour=12, minute=30)
        assert s.atmosphere().time_of_day == TimeOfDay.MIDDAY

    def test_weather_reads_clock_weekday(self, tmp_path: Path):
        s = _build_session(tmp_path)
        sched = s.start_week()
        # start_week resets clock to MON; atmosphere must read MON's
        # daily draw.
        atm = s.atmosphere()
        assert atm.weather.value == sched.daily_weathers["mon"]
        assert atm.weather_tendency.value == sched.weather_tendency

    def test_weather_changes_with_clock_weekday(self, tmp_path: Path):
        s = _build_session(tmp_path)
        sched = s.start_week()
        s.state.clock = WorldClock(week=1, weekday=Weekday.SAT, hour=16, minute=0)
        atm = s.atmosphere()
        assert atm.weather.value == sched.daily_weathers["sat"]

    def test_mood_reflects_simulation_state(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.start_week()
        s.team_morale = -0.6
        s.momentum = 0.0
        assert s.atmosphere().mood == SceneMood.MELANCHOLY
        s.team_morale = 0.5
        s.momentum = 0.5
        assert s.atmosphere().mood == SceneMood.EUPHORIC


# --- grade_paths() --------------------------------------------------------


class TestGradePaths:
    def test_returns_three_paths_to_pngs(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.start_week()
        paths = s.grade_paths()
        assert paths is not None
        assert len(paths) == 3
        for p in paths:
            assert p.exists()
            assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_returns_none_without_init(self, tmp_path: Path):
        s = GameSession.new_game("Alex Morgan", seed=42)
        assert s.grade_paths() is None

    def test_paths_change_when_clock_advances(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.start_week()

        morning_paths = s.grade_paths()  # 08:00 → MORNING
        s.state.clock = WorldClock(week=1, weekday=Weekday.MON, hour=20, minute=0)
        evening_paths = s.grade_paths()
        # The time grade is the first tuple slot.
        assert morning_paths[0] != evening_paths[0]


# --- clock_display() ------------------------------------------------------


class TestClockDisplay:
    def test_default_at_week_start(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.start_week()
        d = s.clock_display()
        assert d.week == 1
        assert d.weekday == Weekday.MON
        assert d.slot == Slot.MORNING
        assert d.hour_minute == "08:00"
        assert d.next_slot_in_minutes == 4 * 60  # 12:00 is 4h away
        assert d.transition_warning is False
        assert d.match_label is None

    def test_transition_warning_at_slot_boundary(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.start_week()
        # 11:45 → 15 minutes to MIDDAY → warning on.
        s.state.clock = WorldClock(week=1, weekday=Weekday.MON, hour=11, minute=45)
        d = s.clock_display()
        assert d.next_slot_in_minutes == 15
        assert d.transition_warning is True

    def test_match_label_overrides_clock_when_set(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.start_week()
        s._active_match_label = "Match vs Northgate"
        d = s.clock_display()
        assert d.match_label == "Match vs Northgate"


# --- Schedule weather round-trip ------------------------------------------


class TestScheduleSerialisation:
    def test_weather_round_trips(self, tmp_path: Path):
        s = _build_session(tmp_path)
        sched = s.start_week()
        d = sched.to_dict()
        from engine.schedule import WeekSchedule

        reloaded = WeekSchedule.from_dict(d)
        assert reloaded.weather_tendency == sched.weather_tendency
        assert reloaded.daily_weathers == sched.daily_weathers
        # Slots round-trip carries weekday + slot fields.
        for orig, copied in zip(sched.slots, reloaded.slots):
            assert orig.weekday == copied.weekday
            assert orig.slot == copied.slot
