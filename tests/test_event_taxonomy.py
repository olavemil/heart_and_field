"""Tests for the event dimensions and chain edges (engine.event_taxonomy, Phase 17)."""

import pytest

import random

from engine.event_taxonomy import (
    CHAIN_EDGES,
    TONE_VALENCE,
    VALID_EVENT_COMBINATIONS,
    ChainDimension,
    EventChainEdge,
    EventDomain,
    EventType,
    EventNature,
    EventTone,
    chains_from,
    is_valid_event_id,
    resolve_event_tone,
)


# --- EventType --------------------------------------------------------------


class TestEventType:
    def test_key_is_essence_domain_nature(self):
        # ADR-001: tone is no longer part of the identity key.
        eid = EventType(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.HOSTILE,
        )
        assert eid.key() == "relationship_confrontation"

    def test_single_tone_populates_possible_tones(self):
        eid = EventType(
            nature=EventNature.ADMISSION,
            domain=EventDomain.PERSONAL,
            tone=EventTone.MELANCHOLY,
        )
        assert eid.possible_tones == frozenset({EventTone.MELANCHOLY})
        assert eid.tone is EventTone.MELANCHOLY  # representative bridge

    def test_round_trip_via_dict_preserves_tone_set(self):
        eid = EventType(
            nature=EventNature.ADMISSION,
            domain=EventDomain.PERSONAL,
            possible_tones=frozenset({EventTone.MELANCHOLY, EventTone.WARM}),
        )
        restored = EventType.from_dict(eid.to_dict())
        assert restored == eid  # essence equality
        assert restored.possible_tones == eid.possible_tones

    def test_from_dict_accepts_legacy_single_tone(self):
        restored = EventType.from_dict(
            {"domain": "personal", "nature": "admission", "tone": "melancholy"}
        )
        assert restored.possible_tones == frozenset({EventTone.MELANCHOLY})

    def test_identity_includes_tone_set(self):
        # Same domain/nature but different tone sets → DIFFERENT types
        # (natural identity; ADR-001 corrected).
        a = EventType(EventNature.CONFRONTATION, EventDomain.RELATIONSHIP,
                      tone=EventTone.HOSTILE)
        b = EventType(EventNature.CONFRONTATION, EventDomain.RELATIONSHIP,
                      tone=EventTone.TENSE)
        assert a != b
        assert {a, b} == {a, b}
        # Identical descriptors collapse.
        c = EventType(EventNature.CONFRONTATION, EventDomain.RELATIONSHIP,
                      tone=EventTone.HOSTILE)
        assert a == c
        assert hash(a) == hash(c)

    def test_from_key_round_trips_essence(self):
        eid = EventType(nature=EventNature.OBSERVATION, domain=EventDomain.SECRET)
        assert EventType.from_key(eid.key()) == eid

    def test_invalid_key_rejected(self):
        with pytest.raises(ValueError):
            EventType.from_key("onlyone")


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


# --- Tone resolver (Phase 25.2) ------------------------------------------


class TestToneResolver:
    def _et(self, *tones):
        return EventType(
            EventNature.INVITATION, EventDomain.RELATIONSHIP,
            possible_tones=frozenset(tones),
        )

    def _dist(self, et, n=4000, **kw):
        rng = random.Random(13)
        counts: dict = {}
        for _ in range(n):
            t = resolve_event_tone(et, rng=rng, **kw)
            counts[t] = counts.get(t, 0) + 1
        return counts

    def test_valence_covers_all_tones(self):
        for t in EventTone:
            assert t in TONE_VALENCE

    def test_single_tone_is_deterministic(self):
        et = self._et(EventTone.ROMANTIC)
        # Even with a strong contrary context, a one-tone type yields it.
        assert resolve_event_tone(
            et, rng=random.Random(1), morale=-1.0
        ) is EventTone.ROMANTIC

    def test_empty_falls_back_to_neutral(self):
        et = EventType(EventNature.OBSERVATION, EventDomain.SPORT)  # no tones
        assert resolve_event_tone(et, rng=random.Random(1)) is EventTone.NEUTRAL

    def test_deterministic_under_fixed_rng(self):
        et = self._et(EventTone.TENSE, EventTone.WARM, EventTone.NEUTRAL)
        a = [resolve_event_tone(et, rng=random.Random(5)) for _ in range(3)]
        b = [resolve_event_tone(et, rng=random.Random(5)) for _ in range(3)]
        assert a == b

    def test_carried_tone_persists(self):
        et = self._et(EventTone.TENSE, EventTone.WARM, EventTone.ROMANTIC)
        without = self._dist(et)
        withp = self._dist(et, carried_tone=EventTone.WARM)
        assert withp[EventTone.WARM] > without[EventTone.WARM]

    def test_context_pulls_toward_mood(self):
        et = self._et(EventTone.HOSTILE, EventTone.WARM)
        up = self._dist(et, morale=1.0, momentum=1.0)
        down = self._dist(et, morale=-1.0, momentum=-1.0)
        assert up[EventTone.WARM] > down[EventTone.WARM]
        assert down[EventTone.HOSTILE] > up[EventTone.HOSTILE]

    def test_carried_adjacency_boosts_near_tone(self):
        # Carried PLAYFUL (0.5) isn't available; WARM (0.6) is adjacent.
        et = self._et(EventTone.WARM, EventTone.HOSTILE)
        without = self._dist(et)
        withadj = self._dist(et, carried_tone=EventTone.PLAYFUL)
        assert withadj[EventTone.WARM] > without[EventTone.WARM]
