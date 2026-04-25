"""Tests for the world clock and slot grid (engine.clock)."""

import pytest

from engine.clock import (
    SLOT_END_HOUR,
    SLOT_START_HOUR,
    Slot,
    Weekday,
    WorldClock,
    next_slot,
    next_weekday,
    slot_for_hour,
)


# --- Slot mapping ----------------------------------------------------------


class TestSlotForHour:
    def test_anchor_hours(self):
        assert slot_for_hour(8) == Slot.MORNING
        assert slot_for_hour(12) == Slot.MIDDAY
        assert slot_for_hour(16) == Slot.AFTERNOON
        assert slot_for_hour(20) == Slot.EVENING

    def test_within_slot_window(self):
        assert slot_for_hour(11) == Slot.MORNING  # last morning hour
        assert slot_for_hour(15) == Slot.MIDDAY
        assert slot_for_hour(19) == Slot.AFTERNOON
        assert slot_for_hour(23) == Slot.EVENING

    def test_night_hours_return_none(self):
        for h in (0, 1, 4, 7):
            assert slot_for_hour(h) is None

    def test_anchor_table_contiguous(self):
        # 4-hour slots from 08 covering 08–24.
        for slot, start in SLOT_START_HOUR.items():
            assert SLOT_END_HOUR[slot] == start + 4


class TestNextSlot:
    def test_normal_progression(self):
        assert next_slot(Slot.MORNING) == (Slot.MIDDAY, False)
        assert next_slot(Slot.MIDDAY) == (Slot.AFTERNOON, False)
        assert next_slot(Slot.AFTERNOON) == (Slot.EVENING, False)

    def test_evening_rolls_to_next_day(self):
        assert next_slot(Slot.EVENING) == (Slot.MORNING, True)


# --- Weekday rollover ------------------------------------------------------


class TestNextWeekday:
    def test_normal_progression(self):
        assert next_weekday(Weekday.MON) == (Weekday.TUE, False)
        assert next_weekday(Weekday.SAT) == (Weekday.SUN, False)

    def test_sunday_rolls_to_monday_with_week_flag(self):
        assert next_weekday(Weekday.SUN) == (Weekday.MON, True)


# --- WorldClock advance ----------------------------------------------------


class TestAdvanceWithinDay:
    def test_advance_minutes(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=8, minute=0)
        c.advance(45)
        assert c.hour == 8
        assert c.minute == 45

    def test_advance_crosses_hour(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=8, minute=50)
        c.advance(20)
        assert c.hour == 9
        assert c.minute == 10

    def test_advance_zero_is_noop(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=10, minute=30)
        c.advance(0)
        assert c.hour == 10
        assert c.minute == 30

    def test_advance_negative_rejected(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=10, minute=0)
        with pytest.raises(ValueError):
            c.advance(-10)


class TestAdvanceCrossesNight:
    def test_advance_into_night_skips_to_next_morning(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=23, minute=30)
        # 23:30 + 60min would land at 00:30, which is in the night
        # window; the clock must skip to 08:00 of the next day.
        c.advance(60)
        assert c.weekday == Weekday.TUE
        assert c.hour == 8
        assert c.minute == 0

    def test_advance_from_evening_into_next_morning(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=22, minute=0)
        # Cross 24:00 → land in night → skip to 08:00 next day.
        c.advance(180)  # 25:00
        assert c.weekday == Weekday.TUE
        assert c.hour == 8


class TestAdvanceCrossesWeek:
    def test_advance_from_sunday_evening_rolls_week(self):
        c = WorldClock(week=1, weekday=Weekday.SUN, hour=21, minute=0)
        c.advance(60)  # 22:00 SUN — still in evening, no rollover
        assert c.week == 1
        assert c.weekday == Weekday.SUN
        # Push past midnight: lands in night → skipped to MON 08:00.
        c.advance(120)
        assert c.week == 2
        assert c.weekday == Weekday.MON
        assert c.hour == 8

    def test_advance_full_day_chunks_count_weekday_rollovers(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=8, minute=0)
        c.advance(24 * 60 * 7)  # exactly 7 days
        assert c.weekday == Weekday.MON
        assert c.week == 2


# --- Fast-forward ----------------------------------------------------------


class TestFastForwardToSlot:
    def test_forward_within_day(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=9, minute=30)
        delta = c.fast_forward_to_slot(Slot.MIDDAY)
        assert c.hour == 12
        assert c.minute == 0
        assert delta == 150  # 09:30 → 12:00

    def test_forward_to_earlier_slot_wraps_to_next_day(self):
        # Already past MIDDAY; ask for MIDDAY → tomorrow.
        c = WorldClock(week=1, weekday=Weekday.MON, hour=14, minute=0)
        delta = c.fast_forward_to_slot(Slot.MIDDAY)
        assert c.weekday == Weekday.TUE
        assert c.hour == 12
        assert c.minute == 0
        # 14:00 → 12:00 next day = 22 hours.
        assert delta == 22 * 60


class TestMinutesUntilNextSlot:
    def test_at_anchor(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=8, minute=0)
        assert c.minutes_until_next_slot() == 4 * 60

    def test_near_boundary(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=11, minute=45)
        assert c.minutes_until_next_slot() == 15

    def test_in_evening_wraps_to_next_morning(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=22, minute=0)
        # Evening's next slot is MORNING tomorrow at 08:00.
        # 22:00 → 24:00 (skip night to 08:00) — 10 hours.
        assert c.minutes_until_next_slot() == 10 * 60


# --- Slot lookup -----------------------------------------------------------


class TestCurrentSlot:
    def test_in_morning(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=10, minute=0)
        assert c.current_slot() == Slot.MORNING

    def test_in_evening(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=21, minute=0)
        assert c.current_slot() == Slot.EVENING

    def test_in_night_falls_back_to_morning(self):
        # Night is unreachable in normal play (advance skips it), but
        # current_slot must still return something sensible.
        c = WorldClock(week=1, weekday=Weekday.MON, hour=8, minute=0)
        # Force-set to a night hour to exercise the branch.
        c.hour = 3
        assert c.current_slot() == Slot.MORNING


# --- Persistence -----------------------------------------------------------


class TestPersistence:
    def test_round_trip(self):
        c = WorldClock(week=3, weekday=Weekday.THU, hour=14, minute=30)
        d = c.to_dict()
        reloaded = WorldClock.from_dict(d)
        assert reloaded == c

    def test_default_from_empty_dict(self):
        c = WorldClock.from_dict({})
        assert c.week == 1
        assert c.weekday == Weekday.MON
        assert c.hour == 8
        assert c.minute == 0


class TestHourMinuteFormat:
    def test_pads_zeros(self):
        c = WorldClock(week=1, weekday=Weekday.MON, hour=8, minute=5)
        assert c.hour_minute() == "08:05"
        c.minute = 30
        assert c.hour_minute() == "08:30"
