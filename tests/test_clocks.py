"""Tests for engine.clocks — tension accumulators and batch operations."""

from engine.clocks import (
    Clock,
    ClockTick,
    check_triggers,
    force_insert_triggered,
    tick_clocks,
)
from engine.schedule import BlockType, EventSlot, WeekSchedule


class TestClockTick:
    def test_round_trip(self):
        tick = ClockTick(amount=0.3, reason="morale drop")
        d = tick.to_dict()
        restored = ClockTick.from_dict(d)
        assert restored.amount == 0.3
        assert restored.reason == "morale drop"

    def test_defaults(self):
        tick = ClockTick(amount=0.5)
        assert tick.reason == ""


class TestClock:
    def test_tick_accumulates(self):
        clock = Clock(id="c1", target_event_id="evt.1", threshold=1.0)
        triggered = clock.tick(0.3, "first")
        assert not triggered
        assert clock.current == 0.3
        assert len(clock.ticks) == 1

    def test_tick_triggers_at_threshold(self):
        clock = Clock(id="c1", target_event_id="evt.1", threshold=0.5)
        clock.tick(0.3)
        triggered = clock.tick(0.3)
        assert triggered
        assert clock.triggered
        assert clock.current == 0.6

    def test_spent_clock_ignores_further_ticks(self):
        clock = Clock(id="c1", target_event_id="evt.1", threshold=0.5)
        clock.tick(0.6)
        assert clock.triggered
        triggered = clock.tick(0.1)
        assert not triggered
        assert clock.current == 0.6  # unchanged
        assert len(clock.ticks) == 1  # only the first tick

    def test_recurring_clock_can_retrigger(self):
        clock = Clock(
            id="c1", target_event_id="evt.1", threshold=0.5, recurring=True
        )
        clock.tick(0.6)
        assert clock.triggered
        clock.reset()
        assert not clock.triggered
        assert clock.current == 0.0
        assert len(clock.ticks) == 0
        triggered = clock.tick(0.5)
        assert triggered

    def test_round_trip(self):
        clock = Clock(
            id="c1",
            target_event_id="evt.1",
            threshold=0.8,
            recurring=True,
        )
        clock.tick(0.3, "reason_a")
        clock.tick(0.2, "reason_b")
        d = clock.to_dict()
        restored = Clock.from_dict(d)
        assert restored.id == "c1"
        assert restored.target_event_id == "evt.1"
        assert restored.threshold == 0.8
        assert restored.current == 0.5
        assert restored.recurring is True
        assert len(restored.ticks) == 2
        assert restored.ticks[0].reason == "reason_a"

    def test_exact_threshold_triggers(self):
        clock = Clock(id="c1", target_event_id="evt.1", threshold=1.0)
        triggered = clock.tick(1.0)
        assert triggered
        assert clock.triggered


class TestTickClocks:
    def test_batch_tick(self):
        clocks = [
            Clock(id="c1", target_event_id="evt.1", threshold=0.5),
            Clock(id="c2", target_event_id="evt.2", threshold=1.5),
        ]
        triggered = tick_clocks(clocks, 0.6, "weekly passage")
        assert len(triggered) == 1
        assert triggered[0].id == "c1"
        assert clocks[1].current == 0.6

    def test_filter_ids(self):
        clocks = [
            Clock(id="c1", target_event_id="evt.1", threshold=0.5),
            Clock(id="c2", target_event_id="evt.2", threshold=0.5),
        ]
        triggered = tick_clocks(
            clocks, 1.0, "tick", filter_ids={"c2"}
        )
        assert len(triggered) == 1
        assert triggered[0].id == "c2"
        assert clocks[0].current == 0.0  # untouched


class TestCheckTriggers:
    def test_returns_triggered_clocks(self):
        c1 = Clock(id="c1", target_event_id="evt.1", threshold=0.5)
        c2 = Clock(id="c2", target_event_id="evt.2", threshold=1.0)
        c1.tick(1.0)
        triggered = check_triggers([c1, c2])
        assert len(triggered) == 1
        assert triggered[0].id == "c1"


class TestForceInsertTriggered:
    def test_inserts_into_schedule(self):
        clock = Clock(id="c1", target_event_id="conflict.blame_assignment", threshold=0.5)
        clock.tick(1.0)
        sched = WeekSchedule(
            season=1,
            week=1,
            slots=[
                EventSlot(block_type=BlockType.DRAMA),
                EventSlot(block_type=BlockType.TRAINING),
            ],
        )
        inserted = force_insert_triggered([clock], sched)
        assert inserted == ["conflict.blame_assignment"]
        assert sched.slots[0].forced_event_id == "conflict.blame_assignment"

    def test_no_double_insert(self):
        clock = Clock(id="c1", target_event_id="evt.1", threshold=0.5)
        clock.tick(1.0)
        sched = WeekSchedule(
            season=1,
            week=1,
            slots=[
                EventSlot(
                    block_type=BlockType.DRAMA,
                    forced_event_id="evt.1",  # already forced
                ),
                EventSlot(block_type=BlockType.TRAINING),
            ],
        )
        inserted = force_insert_triggered([clock], sched)
        assert inserted == []

    def test_recurring_clock_resets_after_insert(self):
        clock = Clock(
            id="c1",
            target_event_id="evt.1",
            threshold=0.5,
            recurring=True,
        )
        clock.tick(1.0)
        sched = WeekSchedule(
            season=1,
            week=1,
            slots=[EventSlot(block_type=BlockType.DRAMA)],
        )
        force_insert_triggered([clock], sched)
        assert not clock.triggered
        assert clock.current == 0.0

    def test_no_available_slot(self):
        clock = Clock(id="c1", target_event_id="evt.1", threshold=0.5)
        clock.tick(1.0)
        sched = WeekSchedule(
            season=1,
            week=1,
            slots=[
                EventSlot(
                    block_type=BlockType.DRAMA,
                    resolved_event_id="done",
                ),
            ],
        )
        inserted = force_insert_triggered([clock], sched)
        assert inserted == []
