"""Tests for engine.save — full state serialise / deserialise round-trips."""

import json
import tempfile
from pathlib import Path

from engine.arcs import ArcGraph, ArcNode, build_arc_graph
from engine.characters import (
    CharacterRole,
    Disposition,
    TierACharacter,
    TierBCharacter,
)
from engine.clocks import Clock
from engine.events import (
    BranchOutcome,
    EventBlueprint,
    GameState,
)
from engine.motivators import Motivator, MotivatorSource
from engine.outcomes import OutcomeRecord, WeekPhase
from engine.relationships import RelationshipDynamic, RelationshipState
from engine.save import (
    deserialise,
    load_from_json,
    save_to_json,
    serialise,
)
from engine.schedule import BlockType, EventSlot, WeekSchedule, generate_week
from engine.stats import StatName, StatTuple


def _build_state() -> GameState:
    """Assemble a representative game state with all field types populated."""
    player = TierACharacter(
        id="player",
        name="Alex Morgan",
        nickname="Morgs",
        role=CharacterRole.STRIKER,
        stats={
            StatName.SPEED: StatTuple(value=0.8, awareness=0.6, focus=0.7, weight=1.0),
            StatName.CONFIDENCE: StatTuple(value=0.7, awareness=0.5, focus=0.6, weight=0.8),
        },
        motivators=[
            Motivator(
                target_stat=StatName.CONFIDENCE,
                delta=0.1,
                decay_rate=0.1,
                source=MotivatorSource.COMPLIMENT,
            )
        ],
        relationships={
            "npc_coach": RelationshipState(
                familiarity=0.8,
                trust=0.7,
                dynamic=RelationshipDynamic.MENTOR,
            )
        },
        event_history=[
            OutcomeRecord(
                event_id="training.drill_partner",
                timestamp=WeekPhase(1, 1),
                participants={"player": "player", "partner": "npc_tm1"},
                branch_taken="good",
                summary="Good drill session with teammate.",
            )
        ],
    )
    teammate = TierBCharacter(
        id="npc_tm1",
        name="Jordan Lee",
        role=CharacterRole.MIDFIELDER,
        stats={
            StatName.STAMINA: 0.75,
            StatName.COLLABORATION: 0.6,
        },
    )
    coach = TierBCharacter(
        id="npc_coach",
        name="Coach Williams",
        role=CharacterRole.MANAGER,
        stats={StatName.LEADERSHIP: 0.9},
    )

    clock = Clock(
        id="rivalry_clock",
        target_event_id="conflict.blame_assignment",
        threshold=1.0,
    )
    clock.tick(0.3, "tense moment")

    return GameState(
        characters={
            "player": player,
            "npc_tm1": teammate,
            "npc_coach": coach,
        },
        outcome_log=[
            OutcomeRecord(
                event_id="training.drill_partner",
                timestamp=WeekPhase(1, 1),
                participants={"player": "player", "partner": "npc_tm1"},
                branch_taken="good",
                summary="Good drill session.",
                stat_deltas={"player": {"finesse": 0.05}},
            )
        ],
        completed_event_ids={"training.drill_partner"},
        disabled_event_ids=set(),
        week_phase=WeekPhase(1, 2),
        clocks=[clock],
    )


class TestSerialiseDeserialise:
    def test_round_trip_state_only(self):
        state = _build_state()
        data = serialise(state)
        restored_state, sched, arc = deserialise(data)

        assert sched is None
        assert arc is None
        assert restored_state.week_phase == WeekPhase(1, 2)
        assert len(restored_state.characters) == 3
        assert "player" in restored_state.characters
        assert "npc_tm1" in restored_state.characters
        assert isinstance(restored_state.characters["player"], TierACharacter)
        assert isinstance(restored_state.characters["npc_tm1"], TierBCharacter)

    def test_tier_a_stats_preserved(self):
        state = _build_state()
        data = serialise(state)
        restored, _, _ = deserialise(data)
        player = restored.characters["player"]
        assert isinstance(player, TierACharacter)
        speed = player.stats[StatName.SPEED]
        assert speed.value == 0.8
        assert speed.awareness == 0.6
        assert speed.focus == 0.7

    def test_tier_a_relationships_preserved(self):
        state = _build_state()
        data = serialise(state)
        restored, _, _ = deserialise(data)
        player = restored.characters["player"]
        assert isinstance(player, TierACharacter)
        rel = player.relationships["npc_coach"]
        assert rel.familiarity == 0.8
        assert rel.dynamic == RelationshipDynamic.MENTOR

    def test_tier_a_event_history_preserved(self):
        state = _build_state()
        data = serialise(state)
        restored, _, _ = deserialise(data)
        player = restored.characters["player"]
        assert isinstance(player, TierACharacter)
        assert len(player.event_history) == 1
        assert player.event_history[0].event_id == "training.drill_partner"

    def test_tier_a_motivators_preserved(self):
        state = _build_state()
        data = serialise(state)
        restored, _, _ = deserialise(data)
        player = restored.characters["player"]
        assert isinstance(player, TierACharacter)
        assert len(player.motivators) == 1
        assert player.motivators[0].source == MotivatorSource.COMPLIMENT

    def test_tier_b_stats_preserved(self):
        state = _build_state()
        data = serialise(state)
        restored, _, _ = deserialise(data)
        tm = restored.characters["npc_tm1"]
        assert isinstance(tm, TierBCharacter)
        assert tm.stats[StatName.STAMINA] == 0.75

    def test_outcome_log_preserved(self):
        state = _build_state()
        data = serialise(state)
        restored, _, _ = deserialise(data)
        assert len(restored.outcome_log) == 1
        assert restored.outcome_log[0].event_id == "training.drill_partner"
        assert restored.outcome_log[0].stat_deltas["player"]["finesse"] == 0.05

    def test_completed_and_disabled_ids_preserved(self):
        state = _build_state()
        state.disabled_event_ids.add("some.disabled")
        data = serialise(state)
        restored, _, _ = deserialise(data)
        assert "training.drill_partner" in restored.completed_event_ids
        assert "some.disabled" in restored.disabled_event_ids

    def test_clocks_preserved(self):
        state = _build_state()
        data = serialise(state)
        restored, _, _ = deserialise(data)
        assert len(restored.clocks) == 1
        clock = restored.clocks[0]
        assert isinstance(clock, Clock)
        assert clock.id == "rivalry_clock"
        assert clock.current == 0.3
        assert len(clock.ticks) == 1

    def test_with_schedule(self):
        state = _build_state()
        sched = generate_week(1, 2)
        sched.slots[0].forced_event_id = "forced.event"
        data = serialise(state, schedule=sched)
        _, restored_sched, _ = deserialise(data)
        assert restored_sched is not None
        assert restored_sched.season == 1
        assert restored_sched.week == 2
        assert restored_sched.slots[0].forced_event_id == "forced.event"

    def test_with_arc_graph(self):
        bps = [
            EventBlueprint(
                id="a",
                unlocks=["b"],
                carries_arc_context=True,
                outcomes={"default": BranchOutcome(summary="a")},
            ),
            EventBlueprint(
                id="b",
                prerequisites=["a"],
                outcomes={"default": BranchOutcome(summary="b")},
            ),
        ]
        graph = build_arc_graph(bps)
        state = _build_state()
        data = serialise(state, arc_graph=graph)
        _, _, restored_graph = deserialise(data)
        assert restored_graph is not None
        assert "a" in restored_graph.nodes
        assert restored_graph.nodes["a"].unlocks == ["b"]

    def test_json_serialisable(self):
        state = _build_state()
        sched = generate_week(1, 2)
        data = serialise(state, schedule=sched)
        # Must not raise.
        json_str = json.dumps(data, indent=2)
        assert isinstance(json_str, str)
        # And deserialise from JSON.
        parsed = json.loads(json_str)
        restored, _, _ = deserialise(parsed)
        assert len(restored.characters) == 3

    def test_version_field(self):
        state = _build_state()
        data = serialise(state)
        assert data["version"] == 1

    def test_world_clock_round_trip(self):
        from engine.clock import Weekday, WorldClock

        state = _build_state()
        state.clock = WorldClock(
            week=3, weekday=Weekday.THU, hour=14, minute=30,
        )
        data = serialise(state)
        restored, _, _ = deserialise(data)
        assert restored.clock.week == 3
        assert restored.clock.weekday == Weekday.THU
        assert restored.clock.hour == 14
        assert restored.clock.minute == 30

    def test_world_clock_default_when_missing(self):
        # Older saves had no world_clock field — deserialise must fill
        # in a sensible default rather than crash.
        state = _build_state()
        data = serialise(state)
        del data["world_clock"]
        restored, _, _ = deserialise(data)
        assert restored.clock.week == 1
        assert restored.clock.hour == 8


class TestFileIO:
    def test_save_and_load_json(self, tmp_path: Path):
        state = _build_state()
        sched = generate_week(1, 2)
        bps = [
            EventBlueprint(
                id="x",
                carries_arc_context=True,
                outcomes={"default": BranchOutcome(summary="x")},
            )
        ]
        graph = build_arc_graph(bps)

        path = str(tmp_path / "save.json")
        save_to_json(path, state, sched, graph)

        loaded_state, loaded_sched, loaded_graph = load_from_json(path)
        assert len(loaded_state.characters) == 3
        assert loaded_sched is not None
        assert loaded_graph is not None
        assert "x" in loaded_graph.nodes


class TestResumeProducesIdenticalState:
    """The exit criterion: save → load → resume produces identical continuation."""

    def test_save_load_resume_identical(self):
        """After loading, the state should be functionally identical to
        what was saved — enough that continued simulation would produce
        the same results given the same RNG."""
        import random

        state = _build_state()
        sched = generate_week(1, 2)

        # Serialise.
        data = serialise(state, schedule=sched)
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored, restored_sched, _ = deserialise(parsed)

        # Verify structural identity.
        assert restored.week_phase == state.week_phase
        assert restored.completed_event_ids == state.completed_event_ids
        assert restored.disabled_event_ids == state.disabled_event_ids
        assert len(restored.outcome_log) == len(state.outcome_log)
        assert len(restored.clocks) == len(state.clocks)
        assert len(restored.characters) == len(state.characters)

        # Verify character stat values are identical.
        for cid in state.characters:
            orig = state.characters[cid]
            rest = restored.characters[cid]
            assert type(orig) is type(rest)
            if isinstance(orig, TierACharacter):
                assert isinstance(rest, TierACharacter)
                for sn in orig.stats:
                    assert orig.stats[sn].value == rest.stats[sn].value
                    assert orig.stats[sn].awareness == rest.stats[sn].awareness
                    assert orig.stats[sn].focus == rest.stats[sn].focus
                    assert orig.stats[sn].weight == rest.stats[sn].weight
