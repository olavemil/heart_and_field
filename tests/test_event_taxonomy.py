"""Tests for the event dimensions and chain edges (engine.event_taxonomy, Phase 17)."""

import pytest

from engine.event_taxonomy import (
    CHAIN_EDGES,
    VALID_EVENT_COMBINATIONS,
    ChainDimension,
    EventChainEdge,
    EventDomain,
    EventType,
    EventNature,
    EventTone,
    chains_from,
    is_valid_event_id,
)


# --- EventType --------------------------------------------------------------


class TestEventType:
    def test_key_format_matches_addendum(self):
        eid = EventType(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.HOSTILE,
        )
        assert eid.key() == "relationship_confrontation_hostile"

    def test_round_trip_via_dict(self):
        eid = EventType(
            nature=EventNature.ADMISSION,
            domain=EventDomain.PERSONAL,
            tone=EventTone.MELANCHOLY,
        )
        assert EventType.from_dict(eid.to_dict()) == eid

    def test_round_trip_via_key_string(self):
        eid = EventType(
            nature=EventNature.OBSERVATION,
            domain=EventDomain.SECRET,
            tone=EventTone.NEUTRAL,
        )
        assert EventType.from_key(eid.key()) == eid

    def test_invalid_key_rejected(self):
        with pytest.raises(ValueError):
            EventType.from_key("only_two")

    def test_frozen_hashable(self):
        a = EventType(EventNature.OBSERVATION, EventDomain.SECRET, EventTone.NEUTRAL)
        b = EventType(EventNature.OBSERVATION, EventDomain.SECRET, EventTone.NEUTRAL)
        assert hash(a) == hash(b)
        assert {a, b} == {a}


# --- VALID_EVENT_COMBINATIONS --------------------------------------------


class TestValidCombinations:
    def test_authored_combo_is_valid(self):
        eid = EventType(
            EventNature.CONFRONTATION, EventDomain.RELATIONSHIP, EventTone.HOSTILE,
        )
        assert is_valid_event_id(eid)

    def test_unauthored_combo_is_invalid(self):
        # SPORT + ADMISSION + ROMANTIC isn't on the addendum's curated list.
        eid = EventType(
            EventNature.ADMISSION, EventDomain.SPORT, EventTone.ROMANTIC,
        )
        assert not is_valid_event_id(eid)

    def test_every_secret_combo_uses_secret_domain(self):
        # Secret-domain events should never accidentally bind to other
        # domains in the registry.
        for eid in VALID_EVENT_COMBINATIONS:
            if eid.domain == EventDomain.SECRET:
                assert eid in VALID_EVENT_COMBINATIONS

    def test_combinations_are_unique(self):
        # frozenset already enforces this; assert just to make the
        # invariant visible to anyone reading the tests.
        assert len(VALID_EVENT_COMBINATIONS) == len(set(VALID_EVENT_COMBINATIONS))

    def test_size_within_expected_range(self):
        # Addendum §4.4 lists ~50 combos across all domains. Sanity
        # check the count so accidental drops surface.
        assert 30 < len(VALID_EVENT_COMBINATIONS) < 100


# --- ChainEdges ----------------------------------------------------------


class TestChainEdges:
    def test_round_trip(self):
        edge = CHAIN_EDGES[0]
        d = edge.to_dict()
        assert EventChainEdge.from_dict(d) == edge

    def test_chains_from_filters_by_origin(self):
        origin = EventType(
            EventNature.CONFRONTATION, EventDomain.RELATIONSHIP, EventTone.HOSTILE,
        )
        edges = chains_from(origin)
        assert all(e.from_id == origin for e in edges)
        assert len(edges) >= 2  # at least the two SCENE edges authored

    def test_chains_from_dimension_filter(self):
        origin = EventType(
            EventNature.CONFRONTATION, EventDomain.RELATIONSHIP, EventTone.HOSTILE,
        )
        only_scene = chains_from(origin, dimensions=frozenset({ChainDimension.SCENE}))
        assert all(e.dimension == ChainDimension.SCENE for e in only_scene)

    def test_chain_endpoints_are_valid_event_ids(self):
        for edge in CHAIN_EDGES:
            assert is_valid_event_id(edge.from_id), (
                f"chain origin {edge.from_id.key()} not in VALID_EVENT_COMBINATIONS"
            )
            assert is_valid_event_id(edge.to_id), (
                f"chain target {edge.to_id.key()} not in VALID_EVENT_COMBINATIONS"
            )

    def test_chain_with_condition_round_trips(self):
        edge = next(e for e in CHAIN_EDGES if e.condition is not None)
        d = edge.to_dict()
        assert EventChainEdge.from_dict(d).condition == edge.condition
