"""Tests for character placeholders (engine.placeholders, Phase 15)."""

import pytest

from engine.characters import CharacterRole, TierBCharacter
from engine.events import GameState
from engine.placeholders import (
    CharacterPlaceholder,
    due_placeholders,
    placeholder_ids_in_secret,
    resolve_placeholder,
    unresolved_references,
)
from engine.secrets import (
    AgendaAspect,
    AgendaGoal,
    AgendaMethod,
    HistoryAspect,
    HistoryEventType,
    RelationType,
    RelationshipAspect,
    Secret,
    SecretCategory,
    SecretMembership,
    SecretRole,
)


# --- CharacterPlaceholder dataclass ---------------------------------------


class TestCharacterPlaceholder:
    def test_round_trip_full(self):
        p = CharacterPlaceholder(
            id="p_sister",
            required_role=CharacterRole.STRIKER,
            required_relation=RelationType.SIBLING,
            scheduling_priority=0.7,
            introduction_event_tags=["family", "vulnerability"],
            secret_ids=["s1", "s2"],
            suggested_name="Maria",
        )
        assert CharacterPlaceholder.from_dict(p.to_dict()) == p

    def test_round_trip_minimal(self):
        p = CharacterPlaceholder(
            id="p_x",
            required_role=CharacterRole.MIDFIELDER,
        )
        round = CharacterPlaceholder.from_dict(p.to_dict())
        assert round.required_relation is None
        assert round.suggested_name is None
        assert round.introduction_event_tags == []


# --- Reference discovery --------------------------------------------------


class TestPlaceholderIdsInSecret:
    def test_relationship_target_picked_up(self):
        s = Secret(
            id="s",
            category=SecretCategory.CONNECTION,
            aspects=[RelationshipAspect(
                id="r", relation=RelationType.PARENT, target="p_father",
            )],
        )
        assert placeholder_ids_in_secret(s) == {"p_father"}

    def test_history_shared_and_known(self):
        s = Secret(
            id="s",
            category=SecretCategory.HISTORY,
            aspects=[HistoryAspect(
                id="h",
                event_type=HistoryEventType.BETRAYAL,
                shared_with=["p_a", "p_b"],
                known_to=["witness1"],
            )],
        )
        assert placeholder_ids_in_secret(s) == {"p_a", "p_b", "witness1"}

    def test_agenda_target(self):
        s = Secret(
            id="s",
            category=SecretCategory.AGENDA,
            aspects=[AgendaAspect(
                id="a", goal=AgendaGoal.GAIN_LEVERAGE,
                method=AgendaMethod.OBSERVING, target="p_rival",
            )],
        )
        assert placeholder_ids_in_secret(s) == {"p_rival"}

    def test_no_target_no_ids(self):
        s = Secret(
            id="s",
            category=SecretCategory.AGENDA,
            aspects=[AgendaAspect(
                id="a", goal=AgendaGoal.GAIN_LEVERAGE,
                method=AgendaMethod.OBSERVING,
            )],
        )
        assert placeholder_ids_in_secret(s) == set()


class TestUnresolvedReferences:
    def test_only_dangling_ids_returned(self):
        state = GameState()
        # Real character with id "real".
        state.characters["real"] = TierBCharacter(
            id="real", name="Real", role=CharacterRole.STRIKER,
        )
        state.secrets["s1"] = Secret(
            id="s1",
            category=SecretCategory.CONNECTION,
            aspects=[
                RelationshipAspect(id="r1", relation=RelationType.SIBLING, target="real"),
                RelationshipAspect(id="r2", relation=RelationType.PARENT, target="p_dad"),
            ],
        )
        state.secrets["s2"] = Secret(
            id="s2",
            category=SecretCategory.HISTORY,
            aspects=[HistoryAspect(
                id="h", event_type=HistoryEventType.SHARED_LOSS,
                shared_with=["p_dad", "p_mom"],
            )],
        )
        out = unresolved_references(state)
        assert "real" not in out
        assert out["p_dad"] == {"s1", "s2"}
        assert out["p_mom"] == {"s2"}


# --- Resolution -----------------------------------------------------------


def _state_with_placeholder() -> GameState:
    state = GameState()
    state.placeholders["p_sister"] = CharacterPlaceholder(
        id="p_sister",
        required_role=CharacterRole.MIDFIELDER,
        required_relation=RelationType.SIBLING,
        suggested_name="Maria",
        secret_ids=["s1"],
    )
    state.secrets["s1"] = Secret(
        id="s1",
        category=SecretCategory.CONNECTION,
        aspects=[RelationshipAspect(
            id="r", relation=RelationType.SIBLING, target="p_sister",
        )],
        memberships=[SecretMembership(
            character_id="player", role=SecretRole.OWNER, exposure=1.0,
        )],
    )
    return state


class TestResolvePlaceholder:
    def test_creates_character_with_placeholder_id(self):
        state = _state_with_placeholder()
        char = resolve_placeholder(state, "p_sister")
        assert char.id == "p_sister"  # id reused so existing aspects keep working
        assert char.role == CharacterRole.MIDFIELDER
        assert "p_sister" in state.characters
        assert "p_sister" not in state.placeholders

    def test_uses_suggested_name_when_no_override(self):
        state = _state_with_placeholder()
        char = resolve_placeholder(state, "p_sister")
        assert char.name == "Maria"

    def test_explicit_name_wins(self):
        state = _state_with_placeholder()
        char = resolve_placeholder(state, "p_sister", name="Lucia")
        assert char.name == "Lucia"

    def test_existing_aspect_target_resolves_to_real_character(self):
        state = _state_with_placeholder()
        resolve_placeholder(state, "p_sister", name="Lucia")
        # The aspect didn't change — it still references "p_sister".
        # Now there's a character with that id, so lookups work.
        assert state.secrets["s1"].aspects[0].target == "p_sister"
        assert state.characters["p_sister"].name == "Lucia"

    def test_unknown_placeholder_raises(self):
        state = GameState()
        with pytest.raises(KeyError):
            resolve_placeholder(state, "p_ghost")

    def test_id_collision_raises(self):
        state = _state_with_placeholder()
        # Manually plant a real character with the placeholder's id.
        state.characters["p_sister"] = TierBCharacter(
            id="p_sister", name="Imposter", role=CharacterRole.STRIKER,
        )
        with pytest.raises(ValueError):
            resolve_placeholder(state, "p_sister")

    def test_factory_hook_for_richer_generators(self):
        state = _state_with_placeholder()

        def factory(p, name):
            # Simulate a future random-character creator.
            return TierBCharacter(
                id=p.id, name=name + " (factory)", role=p.required_role,
            )

        char = resolve_placeholder(state, "p_sister", character_factory=factory)
        assert char.name == "Maria (factory)"


# --- Scheduling ---------------------------------------------------------


def _build_with_priorities() -> GameState:
    state = GameState()
    state.placeholders["p_a"] = CharacterPlaceholder(
        id="p_a", required_role=CharacterRole.STRIKER,
        scheduling_priority=0.3,
        introduction_event_tags=["family"],
    )
    state.placeholders["p_b"] = CharacterPlaceholder(
        id="p_b", required_role=CharacterRole.MIDFIELDER,
        scheduling_priority=0.9,
        introduction_event_tags=["family", "vulnerability"],
    )
    state.placeholders["p_c"] = CharacterPlaceholder(
        id="p_c", required_role=CharacterRole.DEFENDER,
        scheduling_priority=0.5,
        introduction_event_tags=[],  # flexible
    )
    return state


class TestDuePlaceholders:
    def test_filters_by_event_tag(self):
        state = _build_with_priorities()
        out = due_placeholders(state, witnessed_event_tags=["vulnerability"])
        ids = [p.id for p in out]
        # p_b matches via "vulnerability"; p_c is flexible → always due.
        # p_a tags don't include vulnerability.
        assert set(ids) == {"p_b", "p_c"}

    def test_orders_by_priority_desc(self):
        state = _build_with_priorities()
        out = due_placeholders(state, witnessed_event_tags=["family"])
        # Both p_a (0.3) and p_b (0.9) match "family"; p_c flexible.
        priorities = [p.scheduling_priority for p in out]
        assert priorities == sorted(priorities, reverse=True)
        ids = [p.id for p in out]
        assert ids[0] == "p_b"  # highest priority first

    def test_empty_witnessed_returns_only_flexible(self):
        state = _build_with_priorities()
        out = due_placeholders(state, witnessed_event_tags=[])
        ids = {p.id for p in out}
        assert ids == {"p_c"}  # only the empty-tag-list placeholder

    def test_no_placeholders_returns_empty(self):
        state = GameState()
        assert due_placeholders(state, witnessed_event_tags=["any"]) == []


# --- Save round-trip ------------------------------------------------------


class TestSaveRoundTrip:
    def test_placeholders_persist(self):
        from engine.save import deserialise, serialise

        state = _build_with_priorities()
        data = serialise(state)
        restored, _, _ = deserialise(data)
        assert set(restored.placeholders.keys()) == {"p_a", "p_b", "p_c"}
        b = restored.placeholders["p_b"]
        assert b.scheduling_priority == 0.9
        assert b.introduction_event_tags == ["family", "vulnerability"]

    def test_legacy_save_without_placeholders_loads(self):
        from engine.save import deserialise, serialise

        state = GameState()
        data = serialise(state)
        # Older saves had no placeholders field; remove it to verify
        # deserialise tolerates the absence.
        del data["placeholders"]
        restored, _, _ = deserialise(data)
        assert restored.placeholders == {}
