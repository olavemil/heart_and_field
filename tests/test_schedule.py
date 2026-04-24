"""Tests for engine.schedule — week schedule and skeleton generation."""

from engine.schedule import (
    BlockType,
    EventSlot,
    WeekSchedule,
    generate_week,
)


class TestEventSlot:
    def test_to_dict_round_trip(self):
        slot = EventSlot(
            block_type=BlockType.DRAMA,
            forced_event_id="forced.1",
            resolved_event_id="resolved.1",
            resolved_branch="branch_a",
        )
        d = slot.to_dict()
        restored = EventSlot.from_dict(d)
        assert restored.block_type == BlockType.DRAMA
        assert restored.forced_event_id == "forced.1"
        assert restored.resolved_event_id == "resolved.1"
        assert restored.resolved_branch == "branch_a"
        assert restored.phase_index == -1

    def test_game_phase_slot(self):
        slot = EventSlot(block_type=BlockType.GAME_PHASE, phase_index=3)
        d = slot.to_dict()
        restored = EventSlot.from_dict(d)
        assert restored.phase_index == 3

    def test_defaults(self):
        slot = EventSlot(block_type=BlockType.TRAINING)
        assert slot.forced_event_id is None
        assert slot.resolved_event_id is None
        assert slot.resolved_branch is None
        assert slot.phase_index == -1


class TestWeekSchedule:
    def test_pending_slots(self):
        sched = WeekSchedule(
            season=1,
            week=1,
            slots=[
                EventSlot(block_type=BlockType.DRAMA),
                EventSlot(
                    block_type=BlockType.TRAINING,
                    resolved_event_id="train.1",
                ),
                EventSlot(block_type=BlockType.PREGAME),
            ],
        )
        pending = sched.pending_slots()
        assert len(pending) == 2
        assert pending[0].block_type == BlockType.DRAMA
        assert pending[1].block_type == BlockType.PREGAME

    def test_force_next_any_slot(self):
        sched = WeekSchedule(
            season=1,
            week=2,
            slots=[
                EventSlot(
                    block_type=BlockType.DRAMA,
                    resolved_event_id="done",
                ),
                EventSlot(block_type=BlockType.TRAINING),
                EventSlot(block_type=BlockType.PREGAME),
            ],
        )
        ok = sched.force_next("conflict.blame_assignment")
        assert ok
        assert sched.slots[1].forced_event_id == "conflict.blame_assignment"
        # Pregame should still be unfilled.
        assert sched.slots[2].forced_event_id is None

    def test_force_next_with_block_type_filter(self):
        sched = WeekSchedule(
            season=1,
            week=1,
            slots=[
                EventSlot(block_type=BlockType.DRAMA),
                EventSlot(block_type=BlockType.TRAINING),
                EventSlot(block_type=BlockType.PREGAME),
            ],
        )
        ok = sched.force_next("pregame.ritual", block_type=BlockType.PREGAME)
        assert ok
        assert sched.slots[2].forced_event_id == "pregame.ritual"
        # Drama/training should be untouched.
        assert sched.slots[0].forced_event_id is None
        assert sched.slots[1].forced_event_id is None

    def test_force_next_no_matching_slot(self):
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
        ok = sched.force_next("anything")
        assert not ok

    def test_to_dict_round_trip(self):
        sched = generate_week(2, 5, game_phases=4, drama_slots=1)
        sched.slots[0].forced_event_id = "forced.event"
        sched.slots[1].resolved_event_id = "resolved.event"
        d = sched.to_dict()
        restored = WeekSchedule.from_dict(d)
        assert restored.season == 2
        assert restored.week == 5
        assert len(restored.slots) == len(sched.slots)
        assert restored.slots[0].forced_event_id == "forced.event"
        assert restored.slots[1].resolved_event_id == "resolved.event"


class TestGenerateWeek:
    def test_default_skeleton(self):
        sched = generate_week(1, 1)
        types = [s.block_type for s in sched.slots]
        # 2 drama + 1 training + 1 pregame + 8 game + 1 postgame + 1 downtime
        assert types.count(BlockType.DRAMA) == 2
        assert types.count(BlockType.TRAINING) == 1
        assert types.count(BlockType.PREGAME) == 1
        assert types.count(BlockType.GAME_PHASE) == 8
        assert types.count(BlockType.POSTGAME) == 1
        assert types.count(BlockType.DOWNTIME) == 1
        assert len(sched.slots) == 14

    def test_custom_parameters(self):
        sched = generate_week(
            1, 3, game_phases=4, drama_slots=3, training_slots=2, include_downtime=False
        )
        types = [s.block_type for s in sched.slots]
        assert types.count(BlockType.DRAMA) == 3
        assert types.count(BlockType.TRAINING) == 2
        assert types.count(BlockType.GAME_PHASE) == 4
        assert types.count(BlockType.DOWNTIME) == 0

    def test_game_phase_indices(self):
        sched = generate_week(1, 1, game_phases=4)
        game_slots = [s for s in sched.slots if s.block_type == BlockType.GAME_PHASE]
        assert [s.phase_index for s in game_slots] == [0, 1, 2, 3]

    def test_ordering(self):
        sched = generate_week(1, 1)
        types = [s.block_type for s in sched.slots]
        # Drama comes before training, training before pregame, etc.
        drama_end = max(i for i, t in enumerate(types) if t == BlockType.DRAMA)
        training_idx = types.index(BlockType.TRAINING)
        pregame_idx = types.index(BlockType.PREGAME)
        game_start = types.index(BlockType.GAME_PHASE)
        postgame_idx = types.index(BlockType.POSTGAME)
        assert drama_end < training_idx < pregame_idx < game_start < postgame_idx
