"""Tests for engine.session — GameSession facade and headless week playthrough.

Phase 6 exit criteria: a full week runs end-to-end (drama → training →
pregame → game phases → postgame → downtime), save/load round-trips,
and resume produces identical state.
"""

import json
import random

import numpy as np

from engine.characters import CharacterRole, TierACharacter, TierBCharacter
from engine.clocks import Clock
from engine.schedule import BlockType
from engine.session import GameSession
from engine.stats import StatName, StatTuple


def _build_session(seed: int = 42) -> GameSession:
    """Create a session with a player + small roster."""
    session = GameSession.new_game("Alex Morgan", seed=seed)

    roster = {
        "tm_jordan": TierBCharacter(
            id="tm_jordan",
            name="Jordan Lee",
            role=CharacterRole.MIDFIELDER,
            stats={
                StatName.STAMINA: 0.7,
                StatName.COLLABORATION: 0.6,
                StatName.LEADERSHIP: 0.5,
                StatName.SPEED: 0.6,
                StatName.STRENGTH: 0.5,
                StatName.FINESSE: 0.6,
                StatName.CONFIDENCE: 0.5,
                StatName.MOTIVATION: 0.6,
            },
        ),
        "tm_sam": TierBCharacter(
            id="tm_sam",
            name="Sam Carter",
            role=CharacterRole.DEFENDER,
            stats={
                StatName.STAMINA: 0.7,
                StatName.STRENGTH: 0.7,
                StatName.SPEED: 0.5,
                StatName.FINESSE: 0.4,
                StatName.COLLABORATION: 0.6,
                StatName.CAUTIOUSNESS: 0.7,
                StatName.CONFIDENCE: 0.5,
                StatName.MOTIVATION: 0.5,
            },
        ),
        "coach_williams": TierBCharacter(
            id="coach_williams",
            name="Coach Williams",
            role=CharacterRole.MANAGER,
            stats={
                StatName.LEADERSHIP: 0.9,
                StatName.MOTIVATION: 0.7,
            },
        ),
    }
    for cid, char in roster.items():
        session.state.characters[cid] = char

    return session


class TestGameSessionConstruction:
    def test_new_game_creates_player(self):
        session = _build_session()
        assert "player" in session.state.characters
        player = session.state.characters["player"]
        assert isinstance(player, TierACharacter)
        assert player.name == "Alex Morgan"

    def test_new_game_loads_content(self):
        session = _build_session()
        assert len(session.blueprints) > 0
        assert len(session.templates) > 0

    def test_new_game_builds_arc_graph(self):
        session = _build_session()
        assert len(session.arc_graph.nodes) > 0


class TestWeekLifecycle:
    def test_start_week_creates_schedule(self):
        session = _build_session()
        sched = session.start_week()
        assert sched is not None
        assert len(sched.slots) > 0

    def test_pending_slots_decreases_after_resolve(self):
        session = _build_session()
        session.start_week()
        initial_pending = len(session.pending_slots())
        assert initial_pending > 0

        # Resolve first non-game slot.
        for idx, slot in session.pending_slots():
            if slot.block_type != BlockType.GAME_PHASE:
                bp = session.select_event_for_slot(idx)
                if bp is not None:
                    cast = session.cast_event(bp)
                    if cast is not None:
                        branch = list(bp.outcomes.keys())[0]
                        session.resolve_event(bp, branch, cast, idx)
                        break

        remaining = len(session.pending_slots())
        assert remaining < initial_pending

    def test_advance_week_increments(self):
        session = _build_session()
        assert session.state.week_phase.week == 1
        session.advance_week()
        assert session.state.week_phase.week == 2


class TestEventFlow:
    def test_select_and_resolve_drama_event(self):
        session = _build_session()
        session.start_week()

        # Find a drama slot.
        drama_slots = [
            (i, s) for i, s in session.pending_slots()
            if s.block_type == BlockType.DRAMA
        ]
        assert len(drama_slots) > 0

        idx, slot = drama_slots[0]
        bp = session.select_event_for_slot(idx)
        # May be None if no drama events match — that's OK for this test.
        if bp is not None:
            cast = session.cast_event(bp)
            if cast is not None:
                choices = session.get_choices(bp)
                assert len(choices) > 0
                branch = list(choices.keys())[0]
                record = session.resolve_event(bp, branch, cast, idx)
                assert record.event_id == bp.id
                assert record.branch_taken == branch
                # Narration is paginated: at least one non-empty page.
                pages = session.narrate_outcome(bp, cast, record)
                assert len(pages) > 0
                assert any(p for p in pages)

    def test_select_and_resolve_training_event(self):
        session = _build_session()
        session.start_week()

        training_slots = [
            (i, s) for i, s in session.pending_slots()
            if s.block_type == BlockType.TRAINING
        ]
        assert len(training_slots) > 0

        idx, slot = training_slots[0]
        bp = session.select_event_for_slot(idx)
        if bp is not None:
            cast = session.cast_event(bp)
            if cast is not None:
                branch = list(bp.outcomes.keys())[0]
                record = session.resolve_event(bp, branch, cast, idx)
                assert record.event_id == bp.id


class TestMatchSimulation:
    def test_setup_and_run_match(self):
        session = _build_session()
        session.setup_match(opponent_rating=0.5)
        assert len(session.opponent) > 0

        for phase in range(8):
            result = session.simulate_game_phase(phase, 8)
            assert result.phase_number == phase
            assert 0 <= result.team_perf <= 2.0  # synergy can push above 1
            assert -1 <= result.momentum <= 1

        assert len(session.match_results) == 8

    def test_evaluate_match(self):
        session = _build_session()
        session.setup_match(opponent_rating=0.5)
        for phase in range(8):
            session.simulate_game_phase(phase, 8)

        eval_result = session.evaluate_match()
        assert "perceived" in eval_result
        assert "mood_delta" in eval_result
        assert "morale_delta" in eval_result
        assert "team_goals" in eval_result


class TestClockIntegration:
    def test_clock_forces_event_into_schedule(self):
        session = _build_session()

        # Add a clock that's already at threshold.
        clock = Clock(
            id="test_clock",
            target_event_id="conflict.blame_assignment",
            threshold=0.5,
        )
        clock.tick(1.0, "test trigger")
        session.state.clocks.append(clock)

        sched = session.start_week()
        # The clock's target should be forced into a slot.
        forced = [s for s in sched.slots if s.forced_event_id == "conflict.blame_assignment"]
        assert len(forced) >= 1


class TestSerialiseDeserialise:
    def test_session_round_trip(self):
        session = _build_session()
        session.start_week()

        # Resolve a couple of slots so we have state to save.
        for idx, slot in session.pending_slots():
            if slot.block_type in (BlockType.DRAMA, BlockType.TRAINING):
                bp = session.select_event_for_slot(idx)
                if bp is not None:
                    cast = session.cast_event(bp)
                    if cast is not None:
                        branch = list(bp.outcomes.keys())[0]
                        session.resolve_event(bp, branch, cast, idx)
                        break

        # Serialise.
        data = session.serialise()
        json_str = json.dumps(data)

        # Deserialise.
        restored = GameSession.deserialise(json.loads(json_str))
        assert len(restored.state.characters) == len(session.state.characters)
        assert len(restored.state.outcome_log) == len(session.state.outcome_log)
        assert restored.state.week_phase == session.state.week_phase

        # Schedule should round-trip.
        assert restored.schedule is not None

    def test_morale_and_momentum_preserved(self):
        session = _build_session()
        session.team_morale = 0.35
        session.momentum = -0.2

        data = session.serialise()
        restored = GameSession.deserialise(data)
        assert restored.team_morale == 0.35
        assert restored.momentum == -0.2


class TestFullWeekHeadless:
    """The Phase 6 exit criterion: a complete week runs headlessly."""

    def test_full_week_end_to_end(self):
        session = _build_session(seed=123)
        sched = session.start_week()

        events_resolved = 0
        game_phases_run = 0
        match_set_up = False

        for i, slot in enumerate(sched.slots):
            if slot.block_type == BlockType.GAME_PHASE:
                if not match_set_up:
                    session.setup_match(opponent_rating=0.5)
                    match_set_up = True
                result = session.simulate_game_phase(slot.phase_index, 8)
                game_phases_run += 1
                # Mark slot resolved.
                slot.resolved_event_id = f"game_phase_{slot.phase_index}"
                continue

            if slot.block_type == BlockType.POSTGAME and match_set_up:
                session.evaluate_match()

            bp = session.select_event_for_slot(i)
            if bp is None:
                slot.resolved_event_id = "none"
                continue

            cast = session.cast_event(bp)
            if cast is None:
                slot.resolved_event_id = "none"
                continue

            branch = list(bp.outcomes.keys())[0]
            record = session.resolve_event(bp, branch, cast, i)
            pages = session.narrate_outcome(bp, cast, record)
            assert len(pages) > 0
            assert any(p for p in pages)
            events_resolved += 1

        # All slots should be resolved.
        assert all(s.resolved_event_id is not None for s in sched.slots)
        assert game_phases_run == 8
        assert events_resolved > 0

        # State should have outcomes.
        assert len(session.state.outcome_log) > 0

        # Save → load → state matches.
        data = session.serialise()
        json_str = json.dumps(data)
        restored = GameSession.deserialise(json.loads(json_str))
        assert len(restored.state.outcome_log) == len(session.state.outcome_log)
        assert restored.state.week_phase == session.state.week_phase

    def test_multi_week_no_crash(self):
        """Two consecutive weeks run without error."""
        session = _build_session(seed=456)

        for week_num in range(2):
            sched = session.start_week()
            match_set_up = False

            for i, slot in enumerate(sched.slots):
                if slot.block_type == BlockType.GAME_PHASE:
                    if not match_set_up:
                        session.setup_match(opponent_rating=0.5)
                        match_set_up = True
                    session.simulate_game_phase(slot.phase_index, 8)
                    slot.resolved_event_id = f"game_phase_{slot.phase_index}"
                    continue

                if slot.block_type == BlockType.POSTGAME and match_set_up:
                    session.evaluate_match()

                bp = session.select_event_for_slot(i)
                if bp is not None:
                    cast = session.cast_event(bp)
                    if cast is not None:
                        branch = list(bp.outcomes.keys())[0]
                        session.resolve_event(bp, branch, cast, i)
                        continue
                slot.resolved_event_id = "none"

            session.advance_week()

        assert session.state.week_phase.week == 3


class TestSlotSummary:
    def test_slot_summary_structure(self):
        session = _build_session()
        session.start_week()
        summary = session.slot_summary()
        assert len(summary) > 0
        first = summary[0]
        assert "block_type" in first
        assert "index" in first
        assert "resolved" in first


class TestBlockRouting:
    """Every authored blueprint must be reachable from some block (22B)."""

    def _authored_blueprints(self):
        from pathlib import Path

        from engine.content_loader import load_blueprints_from_path

        content_root = Path(__file__).resolve().parent.parent / "game" / "content"
        return load_blueprints_from_path(content_root / "events")

    def test_every_blueprint_routes_to_a_block(self):
        from engine.session import BLOCK_TAGS, IN_MATCH_TAGS

        routable = set().union(*BLOCK_TAGS.values())
        unreachable = [
            bp.id
            for bp in self._authored_blueprints()
            if not bp.tags & IN_MATCH_TAGS and not bp.tags & routable
        ]
        assert unreachable == [], (
            f"blueprints unreachable via BLOCK_TAGS: {unreachable}"
        )

    def test_in_match_blueprints_excluded_from_slots(self):
        from engine.session import IN_MATCH_TAGS

        session = _build_session()
        session.blueprints = self._authored_blueprints()
        for block_type in BlockType:
            for bp in session.blueprints_for_block(block_type):
                assert not bp.tags & IN_MATCH_TAGS, (
                    f"{bp.id} is in-match but routed to {block_type}"
                )


class TestSceneIntro:
    """Phase 22D: engine-built pre-choice scene setting."""

    def _blueprint(self, **kwargs):
        from engine.event_taxonomy import (
            EventDomain,
            EventId,
            EventNature,
            EventTone,
        )
        from engine.events import EventBlueprint, LocationCue, RoleSlot

        defaults = dict(
            id="test.intro",
            tags={"conflict"},
            participants=[RoleSlot(role="player", filter=lambda c: True)],
            outcomes={},
            location=LocationCue(spec_id="school", node_name="locker_bay"),
            event_id=EventId(
                nature=EventNature.CONFRONTATION,
                domain=EventDomain.RELATIONSHIP,
                tone=EventTone.HOSTILE,
            ),
        )
        defaults.update(kwargs)
        return EventBlueprint(**defaults)

    def test_intro_names_location_and_cast(self):
        # Target the deterministic assembly — scene_intro() itself may run
        # the result through the LLM when one is available.
        session = _build_session()
        cast = {
            "player": session.state.characters["player"],
            "target": session.state.characters["tm_jordan"],
        }
        intro, others = session._assemble_scene_intro(self._blueprint(), cast)
        assert "Locker bay." in intro
        assert "Jordan Lee" in intro
        assert others == ["Jordan Lee"]
        # HOSTILE tone contributes an atmosphere line.
        assert intro.count(".") >= 3

    def test_intro_empty_without_cue_or_event_id(self):
        """Solo, no location, no event_id → nothing to say."""
        session = _build_session()
        bp = self._blueprint(location=None, event_id=None)
        cast = {"player": session.state.characters["player"]}
        assert session.scene_intro(bp, cast) == ""

    def test_intro_neutral_solo_still_gets_a_line(self):
        """Neutral tone now contributes an atmosphere line so even quiet
        solo scenes aren't blank (Phase 22D variety pass)."""
        from engine.event_taxonomy import (
            EventDomain,
            EventId,
            EventNature,
            EventTone,
        )

        session = _build_session()
        bp = self._blueprint(
            location=None,
            event_id=EventId(
                nature=EventNature.ISOLATION,
                domain=EventDomain.PERSONAL,
                tone=EventTone.NEUTRAL,
            ),
        )
        cast = {"player": session.state.characters["player"]}
        assert session.scene_intro(bp, cast).strip() != ""

    def test_intro_joins_multiple_cast(self):
        session = _build_session()
        cast = {
            "player": session.state.characters["player"],
            "target": session.state.characters["tm_jordan"],
            "other": session.state.characters["tm_sam"],
        }
        intro, others = session._assemble_scene_intro(self._blueprint(), cast)
        assert "and" in intro
        assert "Jordan Lee" in intro and "Sam Carter" in intro
        assert set(others) == {"Jordan Lee", "Sam Carter"}


class TestFocalCharacter:
    def test_prefers_target_role(self):
        session = _build_session()
        cast = {
            "player": session.state.characters["player"],
            "other": session.state.characters["tm_sam"],
            "target": session.state.characters["tm_jordan"],
        }
        assert session.focal_character(cast).id == "tm_jordan"

    def test_falls_back_to_first_nonplayer(self):
        session = _build_session()
        cast = {
            "player": session.state.characters["player"],
            "witness": session.state.characters["tm_sam"],
        }
        assert session.focal_character(cast).id == "tm_sam"

    def test_solo_returns_none(self):
        session = _build_session()
        cast = {"player": session.state.characters["player"]}
        assert session.focal_character(cast) is None


class TestInPhaseMatchEvents:
    """Phase 22F: playable in-phase beats triggered from the match loop."""

    def _phase_result(self, **kw):
        import numpy as np

        from engine.simulation import PhaseResult

        d = dict(
            phase_number=1,
            performances=np.array([0.5]),
            composites=np.array([0.5]),
            team_perf=0.6,
            opp_perf=0.4,
            momentum=0.5,
            goal_scored=True,
            goal_scorer_index=0,
        )
        d.update(kw)
        return PhaseResult(**d)

    def _session_with_scorer(self):
        """A session whose roster_players()[0] is a teammate (not player)."""
        session = _build_session()
        # tm_jordan is a midfielder teammate; make sure index 0 is them.
        players = session.roster_players()
        # find a teammate index
        idx = next(
            i for i, c in enumerate(players) if c.id != "player"
        )
        return session, idx

    def test_no_event_without_goal(self):
        session = _build_session()
        assert session.select_match_event(self._phase_result(goal_scored=False), 0) is None

    def test_no_event_when_player_scored(self):
        session = _build_session()
        players = session.roster_players()
        player_idx = next(i for i, c in enumerate(players) if c.id == "player")
        r = self._phase_result(goal_scorer_index=player_idx)
        assert session.select_match_event(r, 0) is None

    def test_event_fires_on_teammate_goal(self):
        from unittest.mock import patch

        session, idx = self._session_with_scorer()
        r = self._phase_result(goal_scorer_index=idx)
        # Force the probability gate open.
        with patch("engine.session.MATCH_EVENT_GOAL_CHANCE", 1.0):
            bp = session.select_match_event(r, 0)
        # Only fires if an ingame blueprint is loaded and castable.
        if session._ingame_blueprints():
            assert bp is not None
            assert bp.tags & {"ingame"}

    def test_gate_can_suppress_event(self):
        from unittest.mock import patch

        session, idx = self._session_with_scorer()
        r = self._phase_result(goal_scorer_index=idx)
        with patch("engine.session.MATCH_EVENT_GOAL_CHANCE", 0.0):
            # chance 0 → random() > 0 almost surely True → suppressed
            assert session.select_match_event(r, 0) is None

    def test_cast_pins_scorer(self):
        from engine.events import EventBlueprint, RoleSlot, SceneBlock

        session, idx = self._session_with_scorer()
        scorer = session.roster_players()[idx]
        r = self._phase_result(goal_scorer_index=idx)
        bp = EventBlueprint(
            id="test.huddle",
            tags={"ingame"},
            participants=[
                RoleSlot(role="player", filter=lambda c: c.id == "player"),
                RoleSlot(role="scorer", filter=lambda c: c.id != "player"),
            ],
            blocks=[SceneBlock(id="main")],
            outcomes={},
        )
        cast = session.cast_match_event(bp, r)
        assert cast is not None
        assert cast["scorer"].id == scorer.id
        assert cast["player"].id == "player"

    def test_resolve_match_event_does_not_touch_schedule(self):
        from engine.events import (
            BranchOutcome,
            EventBlueprint,
            RoleSlot,
            SceneBlock,
            StatEffect,
        )
        from engine.stats import StatName

        session, idx = self._session_with_scorer()
        r = self._phase_result(goal_scorer_index=idx)
        session.start_week()
        before = [s.resolved_event_id for s in session.schedule.slots]
        clock_before = (session.state.clock.weekday, session.state.clock.hour)

        bp = EventBlueprint(
            id="test.huddle2",
            tags={"ingame"},
            participants=[
                RoleSlot(role="player", filter=lambda c: c.id == "player"),
                RoleSlot(role="scorer", filter=lambda c: c.id != "player"),
            ],
            blocks=[SceneBlock(id="main")],
            outcomes={
                "warm": BranchOutcome(
                    summary="{They:player} got there first.",
                    stat_effects=[StatEffect("player", StatName.MOTIVATION, 0.03)],
                ),
            },
        )
        cast = session.cast_match_event(bp, r)
        rec = session.resolve_match_event(bp, "warm", cast)
        assert rec is not None
        # No slot marked, clock unmoved — match block owns the time.
        assert [s.resolved_event_id for s in session.schedule.slots] == before
        assert (session.state.clock.weekday, session.state.clock.hour) == clock_before
        assert rec in session.state.outcome_log
