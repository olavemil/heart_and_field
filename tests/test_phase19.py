"""Tests for Phase 19 — chain bias, EventType migration, scene-type wiring."""

from __future__ import annotations

import random

import pytest

from game.engine.characters import CharacterRole, TierACharacter, TierBCharacter
from game.engine.clock import Weekday, WorldClock
from game.engine.event_taxonomy import (
    CHAIN_EDGES,
    VALID_EVENT_COMBINATIONS,
    ChainDimension,
    EventDomain,
    EventType,
    EventNature,
    EventTone,
    chains_from,
)
from game.engine.events import (
    CHAIN_BIAS_BOOST,
    BranchOutcome,
    EventBlueprint,
    GameContext,
    GameState,
    LocationCue,
    RoleSlot,
    SceneBlock,
    StatEffect,
    _chain_bias,
    cast_event,
    compute_weight,
    resolve_outcome,
    select_event,
)
from game.engine.outcomes import OutcomeRecord, WeekPhase
from game.engine.stats import StatName, StatTuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _player() -> TierACharacter:
    return TierACharacter(
        id="player",
        name="Player",
        role=CharacterRole.MIDFIELDER,
        stats={StatName.CONFIDENCE: StatTuple(value=0.5)},
    )


def _npc(name: str = "npc", role: CharacterRole = CharacterRole.DEFENDER) -> TierBCharacter:
    return TierBCharacter(
        id=name,
        name=name.title(),
        role=role,
        stats={StatName.CONFIDENCE: 0.5},
    )


def _state_with(*chars):
    state = GameState(characters={c.id: c for c in chars})
    return state


def _context():
    return GameContext(week_phase=WeekPhase(1, 1))


# ---------------------------------------------------------------------------
# Chain bias tests
# ---------------------------------------------------------------------------


class TestChainBias:
    def test_no_event_id_returns_1(self):
        bp = EventBlueprint(id="test", event_id=None)
        state = GameState()
        assert _chain_bias(bp, state) == 1.0

    def test_empty_log_returns_1(self):
        bp = EventBlueprint(
            id="test",
            event_id=EventType(
                nature=EventNature.ADMISSION,
                domain=EventDomain.RELATIONSHIP,
                tone=EventTone.MELANCHOLY,
            ),
        )
        state = GameState()
        assert _chain_bias(bp, state) == 1.0

    def test_last_outcome_no_taxonomy_id_returns_1(self):
        bp = EventBlueprint(
            id="test",
            event_id=EventType(
                nature=EventNature.ADMISSION,
                domain=EventDomain.RELATIONSHIP,
                tone=EventTone.MELANCHOLY,
            ),
        )
        state = GameState()
        state.outcome_log.append(
            OutcomeRecord(
                event_id="some.event",
                timestamp=WeekPhase(1, 1),
                participants={},
                branch_taken="x",
                summary="x",
                taxonomy_id=None,
            )
        )
        assert _chain_bias(bp, state) == 1.0

    def test_matching_chain_edge_boosts(self):
        """CONFRONTATION(rel,hostile) → ADMISSION(rel,melancholy) is an
        authored chain edge. Blueprint targeting the to_id should get a
        boost."""
        from_id = EventType(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.HOSTILE,
        )
        to_id = EventType(
            nature=EventNature.ADMISSION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.MELANCHOLY,
        )
        # Verify the edge exists in the authored table.
        edges = chains_from(from_id)
        assert any(e.to_id == to_id for e in edges)

        bp = EventBlueprint(id="test", event_id=to_id)
        state = GameState()
        state.outcome_log.append(
            OutcomeRecord(
                event_id="conflict.blame_assignment",
                timestamp=WeekPhase(1, 1),
                participants={},
                branch_taken="escalate",
                summary="x",
                taxonomy_id=from_id,
            )
        )
        assert _chain_bias(bp, state) == CHAIN_BIAS_BOOST

    def test_non_matching_edge_returns_1(self):
        from_id = EventType(
            nature=EventNature.CELEBRATION,
            domain=EventDomain.SPORT,
            tone=EventTone.TRIUMPHANT,
        )
        # Target something that is NOT linked from celebration
        unlinked_id = EventType(
            nature=EventNature.ISOLATION,
            domain=EventDomain.PERSONAL,
            tone=EventTone.MELANCHOLY,
        )
        bp = EventBlueprint(id="test", event_id=unlinked_id)
        state = GameState()
        state.outcome_log.append(
            OutcomeRecord(
                event_id="some.event",
                timestamp=WeekPhase(1, 1),
                participants={},
                branch_taken="x",
                summary="x",
                taxonomy_id=from_id,
            )
        )
        assert _chain_bias(bp, state) == 1.0

    def test_chain_bias_affects_compute_weight(self):
        """compute_weight should apply chain bias multiplier."""
        from_id = EventType(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.HOSTILE,
        )
        to_id = EventType(
            nature=EventNature.ADMISSION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.MELANCHOLY,
        )
        bp = EventBlueprint(
            id="test",
            event_id=to_id,
            participants=[RoleSlot(role="player")],
            outcomes={"a": BranchOutcome(summary="x")},
        )
        p = _player()
        state = _state_with(p)
        ctx = _context()

        # Weight without chain edge
        w_plain = compute_weight(bp, ctx, state)

        # Add matching outcome
        state.outcome_log.append(
            OutcomeRecord(
                event_id="conflict.blame_assignment",
                timestamp=WeekPhase(1, 1),
                participants={},
                branch_taken="escalate",
                summary="x",
                taxonomy_id=from_id,
            )
        )
        w_chained = compute_weight(bp, ctx, state)
        assert w_chained == pytest.approx(w_plain * CHAIN_BIAS_BOOST)


# ---------------------------------------------------------------------------
# OutcomeRecord taxonomy_id round-trip
# ---------------------------------------------------------------------------


class TestOutcomeRecordTaxonomyId:
    def test_taxonomy_id_serialises(self):
        eid = EventType(
            nature=EventNature.CELEBRATION,
            domain=EventDomain.SPORT,
            tone=EventTone.TRIUMPHANT,
        )
        rec = OutcomeRecord(
            event_id="test",
            timestamp=WeekPhase(1, 1),
            participants={},
            branch_taken="x",
            summary="x",
            taxonomy_id=eid,
        )
        d = rec.to_dict()
        assert "taxonomy_id" in d
        restored = OutcomeRecord.from_dict(d)
        assert restored.taxonomy_id == eid

    def test_taxonomy_id_none_omitted(self):
        rec = OutcomeRecord(
            event_id="test",
            timestamp=WeekPhase(1, 1),
            participants={},
            branch_taken="x",
            summary="x",
        )
        d = rec.to_dict()
        assert "taxonomy_id" not in d
        restored = OutcomeRecord.from_dict(d)
        assert restored.taxonomy_id is None


# ---------------------------------------------------------------------------
# resolve_outcome sets taxonomy_id
# ---------------------------------------------------------------------------


class TestResolveOutcomeTaxonomyId:
    def test_taxonomy_id_set_on_record(self):
        eid = EventType(
            nature=EventNature.COLLABORATION,
            domain=EventDomain.SPORT,
            tone=EventTone.NEUTRAL,
        )
        bp = EventBlueprint(
            id="test",
            event_id=eid,
            outcomes={"a": BranchOutcome(summary="x")},
        )
        p = _player()
        state = _state_with(p)
        rec = resolve_outcome(bp, "a", {"player": p}, state)
        assert rec.taxonomy_id == eid

    def test_taxonomy_id_none_when_no_event_id(self):
        bp = EventBlueprint(
            id="test",
            outcomes={"a": BranchOutcome(summary="x")},
        )
        p = _player()
        state = _state_with(p)
        rec = resolve_outcome(bp, "a", {"player": p}, state)
        assert rec.taxonomy_id is None


# ---------------------------------------------------------------------------
# EventType coverage
# ---------------------------------------------------------------------------


class TestEventTypeCoverage:
    def test_all_valid_combinations_have_blueprints(self):
        """Every VALID_EVENT_COMBINATIONS entry is covered by at
        least one blueprint."""
        from pathlib import Path
        from engine.content_loader import load_blueprints_from_path

        content_root = Path(__file__).resolve().parent.parent / "game" / "content"
        bps = load_blueprints_from_path(content_root / "events")
        covered_keys = {bp.event_id.key() for bp in bps if bp.event_id}
        valid_keys = {eid.key() for eid in VALID_EVENT_COMBINATIONS}
        missing = valid_keys - covered_keys
        assert not missing, f"Missing blueprints for: {sorted(missing)}"

    def test_all_blueprint_event_ids_are_valid(self):
        """No blueprint uses an EventType outside the valid set."""
        from pathlib import Path
        from engine.content_loader import load_blueprints_from_path

        content_root = Path(__file__).resolve().parent.parent / "game" / "content"
        bps = load_blueprints_from_path(content_root / "events")
        valid_keys = {eid.key() for eid in VALID_EVENT_COMBINATIONS}
        for bp in bps:
            if bp.event_id is not None:
                assert bp.event_id.key() in valid_keys, (
                    f"{bp.id} has invalid EventType {bp.event_id.key()}"
                )


# ---------------------------------------------------------------------------
# chains_from smoke test
# ---------------------------------------------------------------------------


class TestChainsFrom:
    def test_returns_correct_edges(self):
        from_id = EventType(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.HOSTILE,
        )
        edges = chains_from(from_id)
        assert len(edges) >= 2  # at least hostile→melancholy and hostile→romantic
        to_ids = {e.to_id for e in edges}
        assert EventType(
            nature=EventNature.ADMISSION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.MELANCHOLY,
        ) in to_ids

    def test_dimension_filter(self):
        from_id = EventType(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.HOSTILE,
        )
        scene_only = chains_from(from_id, dimensions=frozenset({ChainDimension.SCENE}))
        for e in scene_only:
            assert e.dimension == ChainDimension.SCENE

    def test_no_edges_returns_empty(self):
        # A valid EventType with no outgoing edges
        eid = EventType(
            nature=EventNature.ISOLATION,
            domain=EventDomain.PERSONAL,
            tone=EventTone.MELANCHOLY,
        )
        assert chains_from(eid) == []
