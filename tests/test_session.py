"""Tests for engine.session — GameSession facade and headless week playthrough.

Phase 6 exit criteria: a full week runs end-to-end (drama → training →
pregame → game phases → postgame → downtime), save/load round-trips,
and resume produces identical state.
"""

import json
import random

import numpy as np

from engine.characters import (
    CharacterRole,
    NON_PLAYING_ROLES,
    TierACharacter,
    TierBCharacter,
)
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

    def test_playing_squad_excludes_staff(self):
        # The generated roster carries a manager + physio. They must
        # never appear in the squad the match simulates.
        session = GameSession.new_game("Alex Morgan", seed=7)
        roster_roles = {c.role for c in session.roster_players()}
        assert CharacterRole.MANAGER in roster_roles  # precondition

        squad = session.playing_squad()
        assert squad, "playing squad should be non-empty"
        assert all(c.role not in NON_PLAYING_ROLES for c in squad)
        assert len(squad) < len(session.roster_players())  # staff removed

    def test_scorer_is_never_non_playing_role(self):
        # Regression (Phase 22F): goal_scorer_index indexes the playing
        # squad, so a manager/physio/coach can never score — both at the
        # narration layer and through ``_scorer_character`` (which feeds
        # the in-match ``goal_huddle`` cast).
        session = GameSession.new_game("Alex Morgan", seed=7)
        session.setup_match(opponent_rating=0.5)
        squad = session.playing_squad()

        scorers = 0
        for _week in range(20):  # many matches' worth of phases
            for phase in range(8):
                result = session.simulate_game_phase(phase, 8)
                if not (result.goal_scored and result.goal_scorer_index is not None):
                    continue
                scorers += 1
                assert result.goal_scorer_index < len(squad)
                # Both consumers of the index must resolve a playing role.
                indexed = squad[result.goal_scorer_index]
                resolved = session._scorer_character(result)
                assert resolved is indexed
                assert indexed.role not in NON_PLAYING_ROLES, (
                    f"non-playing role {indexed.role} resolved as scorer"
                )
            session.match_results.clear()
        assert scorers > 0, "expected at least one goal across 160 phases"


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


class TestNarrativeJournal:
    """Phase 24A — temporal-continuity journal wiring on the session.

    The journal records rendered prose and compresses it at scene
    boundaries. These tests run with the LLM off so the deterministic
    template / fallback paths exercise the wiring without a network.
    """

    def _resolved_event(self, session):
        """Drive selection until one drama/training event resolves.
        Returns ``(blueprint, cast, record)`` or ``None``."""
        session.start_week()
        for idx, slot in session.pending_slots():
            if slot.block_type not in (BlockType.DRAMA, BlockType.TRAINING):
                continue
            bp = session.select_event_for_slot(idx)
            if bp is None:
                continue
            cast = session.cast_event(bp)
            if cast is None:
                continue
            branch = list(bp.outcomes.keys())[0]
            record = session.resolve_event(bp, branch, cast, idx)
            return bp, cast, record
        return None

    def test_narrate_outcome_records_beats(self):
        session = _build_session()
        session.use_llm = False
        resolved = self._resolved_event(session)
        assert resolved is not None, "expected a castable drama/training event"
        bp, cast, record = resolved

        assert session.journal.recent_beats == []
        pages = session.narrate_outcome(bp, cast, record)
        # Every non-empty rendered page is folded into the journal.
        assert session.journal.recent_beats == [p for p in pages if p.strip()]

    def test_scene_intro_records_beat(self):
        session = _build_session()
        session.use_llm = False
        resolved = self._resolved_event(session)
        assert resolved is not None
        bp, cast, _ = resolved

        intro = session.scene_intro(bp, cast)
        if intro:
            assert intro in session.journal.recent_beats

    def test_close_scene_compresses_and_clears(self):
        session = _build_session()
        session.use_llm = False  # deterministic fallback compression
        session.journal.record_beat("Coach pulled Alex aside after training.")
        session.journal.record_beat("Alex held the line and said nothing.")

        summary = session.close_scene()
        assert summary  # deterministic join-and-clamp is non-empty
        assert session.journal.recent_beats == []
        assert session.journal.scene_summaries == [summary]

    def test_close_scene_noop_when_no_open_scene(self):
        session = _build_session()
        session.use_llm = False
        assert session.close_scene() == ""
        assert session.journal.scene_summaries == []

    def test_recent_context_feeds_next_scene(self):
        session = _build_session()
        session.use_llm = False
        session.journal.record_beat("a beat")
        session.close_scene()
        # Verbatim window cleared, but the summary still grounds the next.
        assert session.journal.recent_context() is not None

    def test_journal_round_trips_through_save(self):
        session = _build_session()
        session.journal.record_beat("first beat")
        session.journal.record_scene_summary("a closed scene")
        session.journal.record_beat("an open beat")

        restored = GameSession.deserialise(json.loads(json.dumps(session.serialise())))
        assert restored.journal.recent_beats == session.journal.recent_beats
        assert restored.journal.scene_summaries == session.journal.scene_summaries


class TestEventBeats:
    """Phase 24B — multi-beat event narration (setup → action → reaction
    → result). Run with the LLM off so the deterministic template /
    summary-fallback paths exercise the beat plumbing."""

    def _bp_and_record(self, *, with_extra_beats: bool, with_setup: bool = False):
        from engine.events import BranchOutcome, EventBlueprint, RoleSlot
        from engine.outcomes import OutcomeRecord, WeekPhase

        outcome = BranchOutcome(
            summary="{They:player} settled it, one way or another.",
            action_summary=(
                "{name:player} made the call and moved." if with_extra_beats else None
            ),
            reaction_summary=(
                "{name:target} took it in and answered." if with_extra_beats else None
            ),
        )
        bp = EventBlueprint(
            id="t.beats",
            tags=set(),
            participants=[RoleSlot(role="player"), RoleSlot(role="target")],
            outcomes={"x": outcome},
            setup=("The room waited on {name:player}." if with_setup else None),
        )
        record = OutcomeRecord(
            event_id="t.beats",
            timestamp=WeekPhase(1, 1),
            participants={"player": "player", "target": "tm_jordan"},
            branch_taken="x",
            summary=outcome.summary,
        )
        return bp, record

    def _cast(self, session):
        return {
            "player": session.state.characters["player"],
            "target": session.state.characters["tm_jordan"],
        }

    def test_single_beat_when_no_extra_authored(self):
        session = _build_session()
        session.use_llm = False
        bp, record = self._bp_and_record(with_extra_beats=False)
        beats = session.narrate_event(bp, self._cast(session), record)
        assert [b.kind for b in beats] == ["result"]
        assert all(b.pages for b in beats)

    def test_action_reaction_result_in_order(self):
        session = _build_session()
        session.use_llm = False
        bp, record = self._bp_and_record(with_extra_beats=True)
        beats = session.narrate_event(bp, self._cast(session), record)
        assert [b.kind for b in beats] == ["action", "reaction", "result"]
        assert all(b.pages for b in beats)

    def test_beats_recorded_into_journal_in_order(self):
        session = _build_session()
        session.use_llm = False
        bp, record = self._bp_and_record(with_extra_beats=True)
        session.narrate_event(bp, self._cast(session), record)
        # Every beat's pages land in the journal, action before result.
        joined = " ".join(session.journal.recent_beats)
        assert "made the call" in joined
        assert "took it in" in joined
        assert joined.index("made the call") < joined.index("took it in")

    def test_setup_returns_pages_when_authored(self):
        session = _build_session()
        session.use_llm = False
        bp, _ = self._bp_and_record(with_extra_beats=False, with_setup=True)
        pages = session.narrate_setup(bp, self._cast(session))
        assert pages and any(p.strip() for p in pages)
        assert session.journal.recent_beats == [p for p in pages if p.strip()]

    def test_setup_empty_when_unauthored(self):
        session = _build_session()
        session.use_llm = False
        bp, _ = self._bp_and_record(with_extra_beats=False, with_setup=False)
        assert session.narrate_setup(bp, self._cast(session)) == []

    def test_marquee_event_authors_full_beats(self):
        # Content sanity: the conflict arc opener carries setup + action +
        # reaction on every branch (the 24B authoring pass).
        session = _build_session()
        bp = next(b for b in session.blueprints if b.id == "conflict.blame_assignment")
        assert bp.setup
        for branch, outcome in bp.outcomes.items():
            assert outcome.action_summary, branch
            assert outcome.reaction_summary, branch


class TestArcRecap:
    """Phase 24C — arc callback beat. Surfaces the thread track when an
    arc resumes after a day gap. LLM off → deterministic recap framing."""

    def _prior_blame(self, *, day_ordinal):
        from engine.outcomes import OutcomeRecord, WeekPhase

        return OutcomeRecord(
            event_id="conflict.blame_assignment",
            timestamp=WeekPhase(1, 1),
            participants={"player": "player", "target": "tm_jordan"},
            branch_taken="escalate",
            summary="{They:player} pointed a finger across the dressing room.",
            arc_summary="{They:player} pointed a finger across the dressing room.",
            day_ordinal=day_ordinal,
        )

    def _apology_bp(self, session):
        return next(b for b in session.blueprints if b.id == "conflict.apology")

    def _cast(self, session):
        return {
            "player": session.state.characters["player"],
            "target": session.state.characters["tm_jordan"],
        }

    def _set_day(self, session, *, weekday):
        from engine.clock import Weekday, WorldClock

        session.state.clock = WorldClock(week=1, weekday=weekday)

    def test_recap_fires_after_day_gap(self):
        from engine.clock import Weekday

        session = _build_session()
        session.use_llm = False
        session.state.outcome_log.append(self._prior_blame(day_ordinal=0))  # Mon
        self._set_day(session, weekday=Weekday.WED)  # ordinal 2

        pages = session.narrate_arc_recap(self._apology_bp(session), self._cast(session))
        assert pages and any(p.strip() for p in pages)
        joined = " ".join(pages)
        assert "A couple of days earlier" in joined
        # Recorded into the journal so the resumed scene continues from it.
        assert any("days earlier" in b for b in session.journal.recent_beats)

    def test_no_recap_same_day(self):
        from engine.clock import Weekday

        session = _build_session()
        session.use_llm = False
        session.state.outcome_log.append(self._prior_blame(day_ordinal=0))
        self._set_day(session, weekday=Weekday.MON)  # ordinal 0 == prior

        assert session.narrate_arc_recap(self._apology_bp(session), self._cast(session)) == []

    def test_no_recap_without_prior_arc(self):
        from engine.clock import Weekday

        session = _build_session()
        session.use_llm = False
        self._set_day(session, weekday=Weekday.WED)
        # No prior blame outcome in the log → nothing to recap.
        assert session.narrate_arc_recap(self._apology_bp(session), self._cast(session)) == []

    def test_no_recap_when_prior_day_unknown(self):
        from engine.clock import Weekday

        session = _build_session()
        session.use_llm = False
        session.state.outcome_log.append(self._prior_blame(day_ordinal=None))  # legacy
        self._set_day(session, weekday=Weekday.WED)
        assert session.narrate_arc_recap(self._apology_bp(session), self._cast(session)) == []

    def test_resolve_event_records_day_ordinal(self):
        from engine.clock import Weekday, WorldClock

        session = _build_session()
        session.start_week()
        session.state.clock = WorldClock(week=1, weekday=Weekday.THU)  # ordinal 3
        for idx, slot in session.pending_slots():
            if slot.block_type not in (BlockType.DRAMA, BlockType.TRAINING):
                continue
            bp = session.select_event_for_slot(idx)
            if bp is None:
                continue
            cast = session.cast_event(bp)
            if cast is None:
                continue
            branch = list(bp.outcomes.keys())[0]
            record = session.resolve_event(bp, branch, cast, idx)
            assert record.day_ordinal == 3
            break

    def test_day_ordinal_round_trips(self):
        from engine.clock import Weekday, WorldClock

        session = _build_session()
        session.state.outcome_log.append(self._prior_blame(day_ordinal=5))
        restored = GameSession.deserialise(json.loads(json.dumps(session.serialise())))
        assert restored.state.outcome_log[-1].day_ordinal == 5


class TestPlayerStance:
    """Phase 24C — player stance on blueprints + framing/perspective maps."""

    def test_default_stance_is_actor(self):
        from engine.events import EventBlueprint, PlayerStance

        assert EventBlueprint(id="x").player_stance is PlayerStance.ACTOR

    def test_authored_stances_applied(self):
        from engine.events import PlayerStance

        session = _build_session()
        by_id = {b.id: b for b in session.blueprints}
        # Reactive scenes: the player responds rather than drives.
        assert by_id["conflict.blame_assignment"].player_stance is PlayerStance.REACTOR
        assert by_id["mentor.quiet_word"].player_stance is PlayerStance.REACTOR
        assert by_id["postgame.loss_silence"].player_stance is PlayerStance.REACTOR
        # Onlooker: present but on the edge.
        assert by_id["downtime.travel_reading"].player_stance is PlayerStance.ONLOOKER

    def test_stance_maps_to_framing_and_perspective(self):
        from engine.events import PlayerStance
        from engine.figure_layout import PlayerFraming
        from engine.session import _STANCE_PERSPECTIVE, _STANCE_TO_FRAMING

        # Every stance resolves to a framing; only ACTOR has no note.
        for stance in PlayerStance:
            assert stance in _STANCE_TO_FRAMING
        assert _STANCE_TO_FRAMING[PlayerStance.ACTOR] is PlayerFraming.FOREGROUND
        assert _STANCE_TO_FRAMING[PlayerStance.SPECTATOR] is PlayerFraming.BACKGROUND
        assert PlayerStance.ACTOR not in _STANCE_PERSPECTIVE
        assert PlayerStance.SPECTATOR in _STANCE_PERSPECTIVE

    def test_resolve_event_stamps_resolved_stance(self):
        from engine.events import PlayerStance

        session = _build_session()
        session.start_week()
        for idx, slot in session.pending_slots():
            if slot.block_type not in (BlockType.DRAMA, BlockType.TRAINING):
                continue
            bp = session.select_event_for_slot(idx)
            if bp is None:
                continue
            cast = session.cast_event(bp)
            if cast is None:
                continue
            resolved = session.resolve_player_stance(bp, cast)
            assert session._current_player_stance is resolved
            record = session.resolve_event(bp, list(bp.outcomes)[0], cast, idx)
            # The record carries a valid stance; the per-event cache clears.
            assert record.player_stance == resolved.value
            assert PlayerStance(record.player_stance) is resolved
            assert session._current_player_stance is None
            break

    def test_resolved_stance_persists_as_prior(self):
        # The most recent recorded stance feeds the next resolution as the
        # continuity anchor.
        from engine.events import PlayerStance
        from engine.outcomes import OutcomeRecord, WeekPhase

        session = _build_session()
        session.state.outcome_log.append(
            OutcomeRecord(
                event_id="x", timestamp=WeekPhase(1, 1), participants={},
                branch_taken="b", summary="s",
                player_stance=PlayerStance.SPECTATOR.value,
            )
        )
        assert session._last_player_stance() is PlayerStance.SPECTATOR


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
