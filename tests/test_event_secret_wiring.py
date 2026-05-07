"""Phase 17 — secret + placeholder wiring into select_event/resolve_outcome."""

import random

import pytest

from engine.characters import CharacterRole, TierBCharacter
from engine.events import (
    BranchOutcome,
    EventBlueprint,
    GameContext,
    GameState,
    RoleSlot,
    SceneBlock,
    meets_secret_requirements,
    representative_cast,
    resolve_outcome,
    select_event,
)
from engine.outcomes import WeekPhase
from engine.placeholders import CharacterPlaceholder
from engine.secrets import (
    AgendaAspect,
    AgendaGoal,
    AgendaMethod,
    AspectType,
    HistoryAspect,
    HistoryEventType,
    Secret,
    SecretCategory,
    SecretMembership,
    SecretRole,
)


def _make_state(*chars: TierBCharacter) -> GameState:
    return GameState(characters={c.id: c for c in chars})


def _make_ctx() -> GameContext:
    return GameContext(week_phase=WeekPhase(1, 1))


def _player() -> TierBCharacter:
    return TierBCharacter(
        id="player", name="Player", role=CharacterRole.STRIKER,
    )


# --- Eligibility gating --------------------------------------------------


class TestRequiresAspects:
    def test_blueprint_without_secret_member_filtered(self):
        bp = EventBlueprint(
            id="bp",
            participants=[RoleSlot(role="p", filter=lambda c: c.id == "player")],
            base_weight=1.0,
            outcomes={"x": BranchOutcome(summary="x")},
            requires_aspects=[AspectType.AGENDA],
        )
        # No secrets in state — gate fails.
        state = _make_state(_player())
        out = select_event([bp], _make_ctx(), state, random.Random(0))
        assert out is None

    def test_blueprint_with_matching_secret_passes(self):
        bp = EventBlueprint(
            id="bp",
            participants=[RoleSlot(role="p", filter=lambda c: c.id == "player")],
            base_weight=1.0,
            outcomes={"x": BranchOutcome(summary="x")},
            requires_aspects=[AspectType.AGENDA],
        )
        state = _make_state(_player())
        state.secrets["s"] = Secret(
            id="s",
            category=SecretCategory.AGENDA,
            aspects=[AgendaAspect(
                id="a", goal=AgendaGoal.GAIN_LEVERAGE, method=AgendaMethod.OBSERVING,
            )],
            memberships=[SecretMembership(
                character_id="player", role=SecretRole.OWNER, exposure=1.0,
            )],
        )
        out = select_event([bp], _make_ctx(), state, random.Random(0))
        assert out is bp

    def test_meets_secret_requirements_helper(self):
        state = _make_state(_player())
        state.secrets["s"] = Secret(
            id="s", category=SecretCategory.HISTORY,
            aspects=[HistoryAspect(
                id="h", event_type=HistoryEventType.BETRAYAL,
            )],
            memberships=[SecretMembership(
                character_id="player", role=SecretRole.WITNESS, exposure=0.6,
            )],
        )
        bp_history = EventBlueprint(
            id="bp_h", outcomes={"x": BranchOutcome(summary="x")},
            requires_aspects=[AspectType.HISTORY],
        )
        bp_agenda = EventBlueprint(
            id="bp_a", outcomes={"x": BranchOutcome(summary="x")},
            requires_aspects=[AspectType.AGENDA],
        )
        cast = {"p": state.characters["player"]}
        assert meets_secret_requirements(bp_history, cast, state) is True
        assert meets_secret_requirements(bp_agenda, cast, state) is False


class TestRequiresSecretRole:
    def test_witness_required_blocks_owner_only_cast(self):
        bp = EventBlueprint(
            id="bp",
            participants=[RoleSlot(role="p", filter=lambda c: c.id == "player")],
            base_weight=1.0,
            outcomes={"x": BranchOutcome(summary="x")},
            requires_secret_role=SecretRole.WITNESS,
        )
        state = _make_state(_player())
        state.secrets["s"] = Secret(
            id="s", category=SecretCategory.AGENDA,
            aspects=[AgendaAspect(
                id="a", goal=AgendaGoal.GAIN_LEVERAGE, method=AgendaMethod.OBSERVING,
            )],
            memberships=[SecretMembership(
                character_id="player", role=SecretRole.OWNER, exposure=1.0,
            )],
        )
        assert select_event([bp], _make_ctx(), state, random.Random(0)) is None

    def test_witness_role_in_cast_passes(self):
        bp = EventBlueprint(
            id="bp",
            participants=[RoleSlot(role="p", filter=lambda c: c.id == "player")],
            base_weight=1.0,
            outcomes={"x": BranchOutcome(summary="x")},
            requires_secret_role=SecretRole.WITNESS,
        )
        state = _make_state(_player())
        state.secrets["s"] = Secret(
            id="s", category=SecretCategory.HISTORY,
            aspects=[HistoryAspect(
                id="h", event_type=HistoryEventType.INCIDENT,
            )],
            memberships=[SecretMembership(
                character_id="player", role=SecretRole.WITNESS, exposure=0.5,
            )],
        )
        out = select_event([bp], _make_ctx(), state, random.Random(0))
        assert out is bp


# --- boosted_by_aspects -------------------------------------------------


class TestBoostedByAspects:
    def test_boost_increases_selection_against_unboosted(self):
        state = _make_state(_player())
        state.secrets["s"] = Secret(
            id="s", category=SecretCategory.AGENDA,
            aspects=[AgendaAspect(
                id="a", goal=AgendaGoal.GAIN_LEVERAGE, method=AgendaMethod.OBSERVING,
            )],
            memberships=[SecretMembership(
                character_id="player", role=SecretRole.OWNER, exposure=1.0,
            )],
        )
        boosted = EventBlueprint(
            id="boosted",
            participants=[RoleSlot(role="p", filter=lambda c: c.id == "player")],
            base_weight=1.0,
            outcomes={"x": BranchOutcome(summary="x")},
            boosted_by_aspects=[AspectType.AGENDA],
        )
        plain = EventBlueprint(
            id="plain",
            participants=[RoleSlot(role="p", filter=lambda c: c.id == "player")],
            base_weight=1.0,
            outcomes={"x": BranchOutcome(summary="x")},
        )
        rng = random.Random(7)
        counts = {"boosted": 0, "plain": 0}
        for _ in range(400):
            choice = select_event([boosted, plain], _make_ctx(), state, rng)
            counts[choice.id] += 1
        assert counts["boosted"] > counts["plain"]


# --- reveals_exposure ---------------------------------------------------


class TestRevealsExposure:
    def test_matching_tag_advances_exposure(self):
        state = _make_state(_player())
        state.secrets["s"] = Secret(
            id="s", category=SecretCategory.HISTORY,
            aspects=[HistoryAspect(id="h", event_type=HistoryEventType.SHARED_LOSS)],
            memberships=[SecretMembership(
                character_id="player", role=SecretRole.OWNER, exposure=1.0,
            )],
            reveal_triggers=["postgame"],
            exposure_level=0.1,
        )
        bp = EventBlueprint(
            id="bp",
            tags={"postgame", "vulnerability"},
            outcomes={"x": BranchOutcome(summary="x")},
            reveals_exposure=0.2,
        )
        cast = {"p": state.characters["player"]}
        resolve_outcome(bp, "x", cast, state)
        assert state.secrets["s"].exposure_level == pytest.approx(0.3)

    def test_unrelated_tag_does_not_advance(self):
        state = _make_state(_player())
        state.secrets["s"] = Secret(
            id="s", category=SecretCategory.HISTORY,
            aspects=[HistoryAspect(id="h", event_type=HistoryEventType.SHARED_LOSS)],
            memberships=[SecretMembership(
                character_id="player", role=SecretRole.OWNER, exposure=1.0,
            )],
            reveal_triggers=["postgame"],
            exposure_level=0.1,
        )
        bp = EventBlueprint(
            id="bp",
            tags={"training"},
            outcomes={"x": BranchOutcome(summary="x")},
            reveals_exposure=0.2,
        )
        cast = {"p": state.characters["player"]}
        resolve_outcome(bp, "x", cast, state)
        assert state.secrets["s"].exposure_level == pytest.approx(0.1)

    def test_caps_at_1(self):
        state = _make_state(_player())
        state.secrets["s"] = Secret(
            id="s", category=SecretCategory.HISTORY,
            aspects=[HistoryAspect(id="h", event_type=HistoryEventType.SHARED_LOSS)],
            memberships=[SecretMembership(
                character_id="player", role=SecretRole.OWNER, exposure=1.0,
            )],
            reveal_triggers=["postgame"],
            exposure_level=0.9,
        )
        bp = EventBlueprint(
            id="bp",
            tags={"postgame"},
            outcomes={"x": BranchOutcome(summary="x")},
            reveals_exposure=0.5,
        )
        cast = {"p": state.characters["player"]}
        resolve_outcome(bp, "x", cast, state)
        assert state.secrets["s"].exposure_level == 1.0

    def test_secret_without_cast_member_not_touched(self):
        state = _make_state(_player())
        # Secret carried only by a non-cast character.
        state.secrets["s"] = Secret(
            id="s", category=SecretCategory.AGENDA,
            aspects=[AgendaAspect(
                id="a", goal=AgendaGoal.GAIN_LEVERAGE, method=AgendaMethod.OBSERVING,
            )],
            memberships=[SecretMembership(
                character_id="ghost", role=SecretRole.OWNER, exposure=1.0,
            )],
            reveal_triggers=["postgame"],
            exposure_level=0.2,
        )
        bp = EventBlueprint(
            id="bp",
            tags={"postgame"},
            outcomes={"x": BranchOutcome(summary="x")},
            reveals_exposure=0.5,
        )
        cast = {"p": state.characters["player"]}
        resolve_outcome(bp, "x", cast, state)
        assert state.secrets["s"].exposure_level == pytest.approx(0.2)


# --- introduces_placeholders -------------------------------------------


class TestIntroducesPlaceholders:
    def test_resolves_listed_placeholder(self):
        state = _make_state(_player())
        state.placeholders["p_sister"] = CharacterPlaceholder(
            id="p_sister",
            required_role=CharacterRole.MIDFIELDER,
            suggested_name="Maria",
        )
        bp = EventBlueprint(
            id="bp",
            tags={"family"},
            outcomes={"x": BranchOutcome(summary="x")},
            introduces_placeholders=["p_sister"],
        )
        cast = {"p": state.characters["player"]}
        resolve_outcome(bp, "x", cast, state)
        assert "p_sister" in state.characters
        assert "p_sister" not in state.placeholders
        assert state.characters["p_sister"].name == "Maria"

    def test_silent_skip_when_placeholder_missing(self):
        state = _make_state(_player())
        bp = EventBlueprint(
            id="bp",
            outcomes={"x": BranchOutcome(summary="x")},
            introduces_placeholders=["p_ghost"],
        )
        cast = {"p": state.characters["player"]}
        # Should not raise.
        resolve_outcome(bp, "x", cast, state)
        assert "p_ghost" not in state.characters

    def test_silent_skip_when_already_resolved(self):
        state = _make_state(_player())
        state.placeholders["p_sis"] = CharacterPlaceholder(
            id="p_sis", required_role=CharacterRole.STRIKER,
        )
        # Pre-existing real character with the placeholder's id (id collision).
        state.characters["p_sis"] = TierBCharacter(
            id="p_sis", name="Existing", role=CharacterRole.STRIKER,
        )
        bp = EventBlueprint(
            id="bp", outcomes={"x": BranchOutcome(summary="x")},
            introduces_placeholders=["p_sis"],
        )
        cast = {"p": state.characters["player"]}
        # The early "already in characters" guard skips resolution; no
        # exception escapes resolve_outcome.
        resolve_outcome(bp, "x", cast, state)
        assert state.characters["p_sis"].name == "Existing"
