"""Tests for the secret LLM pipeline (engine.secret_llm, Phase 14).

Uses mock LLMClient implementations to keep the tests deterministic
and offline. The pipeline must work end-to-end whether the LLM returns
clean responses, malformed JSON, ``None``, or is permanently disabled.
"""

import json

import pytest

from engine.llm import LLMClient, LLMPrompt
from engine.secret_llm import (
    _fallback_aspect_phrases,
    _parse_phrases_json,
    compose_mechanical_description,
    flavor_secret,
    generate_aspect_phrases,
    initialise_secret,
    needs_consistency_pass,
    primary_holder,
    reformulate_secret,
)
from engine.secrets import (
    AgendaAspect,
    AgendaGoal,
    AgendaMethod,
    AspectPhrases,
    HistoryAspect,
    HistoryEventType,
    IdentityAspect,
    RelationType,
    RelationshipAspect,
    Secret,
    SecretCategory,
    SecretMembership,
    SecretRole,
    TabooAspect,
    TabooOrigin,
    TabooSubject,
)


# --- Mock clients ---------------------------------------------------------


class MockClient:
    """LLMClient duck-type that returns canned responses in order.

    Each call to :meth:`generate` pops the next response. ``None`` in
    the queue mimics a failed LLM call (graceful fallback path).
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, prompt: LLMPrompt):
        self.calls.append(prompt)
        if not self.responses:
            return None
        return self.responses.pop(0)


class DisabledClient:
    def generate(self, prompt: LLMPrompt):
        return None


# --- Helpers --------------------------------------------------------------


def _good_aspect_response(aspect_id: str = "ignored") -> str:
    return json.dumps({
        "hidden": "Something is off, just out of reach.",
        "glimpsed": "Pieces refuse to settle into place.",
        "suspected": "The shape is clear if you know where to look for it.",
        "known": "The whole thing reads exactly as it is.",
    })


def _basic_secret() -> Secret:
    return Secret(
        id="s1",
        category=SecretCategory.AGENDA,
        aspects=[
            AgendaAspect(
                id="ag",
                goal=AgendaGoal.GAIN_LEVERAGE,
                method=AgendaMethod.OBSERVING,
                target="rival",
            ),
        ],
        memberships=[
            SecretMembership(
                character_id="player",
                role=SecretRole.OWNER,
                exposure=1.0,
            ),
        ],
    )


# --- compose_mechanical_description --------------------------------------


class TestComposeMechanical:
    def test_empty_secret_returns_empty_string(self):
        s = Secret(id="s", category=SecretCategory.AGENDA)
        assert compose_mechanical_description(s, {}) == ""

    def test_relationship_aspect(self):
        s = Secret(
            id="s",
            category=SecretCategory.CONNECTION,
            aspects=[RelationshipAspect(
                id="r",
                relation=RelationType.FORMER_LOVER,
                target="rival",
            )],
            memberships=[SecretMembership(character_id="player", role=SecretRole.OWNER)],
        )
        out = compose_mechanical_description(s, {"player": "Alex", "rival": "Sam"})
        assert "Alex" in out
        assert "former lover" in out
        assert "Sam" in out

    def test_agenda_aspect_inlines_target(self):
        s = _basic_secret()
        out = compose_mechanical_description(
            s, {"player": "Alex", "rival": "Sam"},
        )
        assert "Alex" in out
        assert "observing" in out
        assert "leverage on Sam" in out

    def test_taboo_aspect(self):
        s = Secret(
            id="s",
            category=SecretCategory.TABOO,
            aspects=[TabooAspect(
                id="t",
                subject=TabooSubject.HEALTH_CONDITION,
                origin=TabooOrigin.SHAME,
            )],
            memberships=[SecretMembership(character_id="player", role=SecretRole.OWNER)],
        )
        out = compose_mechanical_description(s, {"player": "Alex"})
        assert "health condition" in out
        assert "shame" in out

    def test_history_aspect_two_shared(self):
        s = Secret(
            id="s",
            category=SecretCategory.HISTORY,
            aspects=[HistoryAspect(
                id="h",
                event_type=HistoryEventType.BETRAYAL,
                shared_with=["a", "b"],
            )],
            memberships=[SecretMembership(character_id="player", role=SecretRole.OWNER)],
        )
        out = compose_mechanical_description(s, {"player": "Alex", "a": "Sam", "b": "Jordan"})
        assert "Alex" in out and "Sam" in out and "Jordan" in out
        assert "betrayal" in out

    def test_identity_aspect(self):
        s = Secret(
            id="s",
            category=SecretCategory.IDENTITY,
            aspects=[IdentityAspect(id="i", fact="real first name is Maria")],
            memberships=[SecretMembership(character_id="player", role=SecretRole.OWNER)],
        )
        out = compose_mechanical_description(s, {"player": "Alex"})
        assert "Alex" in out
        assert "real first name is Maria" in out

    def test_unmapped_id_falls_through(self):
        s = _basic_secret()
        # Both player and rival missing from the cast map.
        out = compose_mechanical_description(s, {})
        # Holder id surfaces as the fallback name so devs can spot
        # missing placeholder bindings.
        assert "player" in out
        assert "rival" in out

    def test_multiple_aspects_joined_with_periods(self):
        s = Secret(
            id="s",
            category=SecretCategory.HISTORY,
            aspects=[
                RelationshipAspect(id="r", relation=RelationType.SIBLING, target="a"),
                HistoryAspect(id="h", event_type=HistoryEventType.SHARED_LOSS, shared_with=["a"]),
            ],
            memberships=[SecretMembership(character_id="player", role=SecretRole.OWNER)],
        )
        out = compose_mechanical_description(s, {"player": "Alex", "a": "Sam"})
        assert out.count(".") >= 2  # one per sentence + final
        assert out.endswith(".")


class TestPrimaryHolder:
    def test_picks_owner_first(self):
        s = Secret(
            id="s", category=SecretCategory.AGENDA,
            memberships=[
                SecretMembership(character_id="w", role=SecretRole.WITNESS),
                SecretMembership(character_id="p", role=SecretRole.PARTICIPANT),
                SecretMembership(character_id="o", role=SecretRole.OWNER),
            ],
        )
        assert primary_holder(s) == "o"

    def test_falls_back_to_participant(self):
        s = Secret(
            id="s", category=SecretCategory.AGENDA,
            memberships=[
                SecretMembership(character_id="w", role=SecretRole.WITNESS),
                SecretMembership(character_id="p", role=SecretRole.PARTICIPANT),
            ],
        )
        assert primary_holder(s) == "p"

    def test_no_memberships_returns_none(self):
        s = Secret(id="s", category=SecretCategory.AGENDA)
        assert primary_holder(s) is None


# --- flavor_secret --------------------------------------------------------


class TestFlavorSecret:
    def test_uses_llm_response_when_available(self):
        s = _basic_secret()
        client = MockClient(["A flavored description."])
        out = flavor_secret(
            client, s, cast={"player": "Alex", "rival": "Sam"},
            character_label="Alex — striker",
        )
        assert out == "A flavored description."
        assert len(client.calls) == 1

    def test_falls_back_to_mechanical_on_none(self):
        s = _basic_secret()
        out = flavor_secret(
            DisabledClient(), s,
            cast={"player": "Alex", "rival": "Sam"},
            character_label="Alex",
        )
        # Mechanical wraps with a period; key facts present.
        assert "Alex" in out
        assert "leverage on Sam" in out

    def test_falls_back_on_empty_response(self):
        s = _basic_secret()
        client = MockClient(["   "])
        out = flavor_secret(
            client, s, cast={"player": "Alex", "rival": "Sam"},
            character_label="Alex",
        )
        # Empty/whitespace LLM response → mechanical fallback.
        assert "Alex" in out
        assert "leverage" in out

    def test_no_aspects_returns_empty(self):
        s = Secret(id="s", category=SecretCategory.AGENDA)
        assert flavor_secret(
            MockClient(["x"]), s, cast={}, character_label="x",
        ) == ""

    def test_uses_existing_mechanical_when_set(self):
        s = _basic_secret()
        s.mechanical = "Pre-existing mechanical."
        client = MockClient([None])
        out = flavor_secret(
            client, s, cast={}, character_label="x",
        )
        assert out == "Pre-existing mechanical."


# --- generate_aspect_phrases ---------------------------------------------


class TestGenerateAspectPhrases:
    def test_parses_clean_json(self):
        s = _basic_secret()
        client = MockClient([_good_aspect_response()])
        phrases = generate_aspect_phrases(
            client, s.aspects[0],
            mechanical="Alex is observing in order to gain leverage on Sam.",
            description="Alex watches Sam.",
        )
        assert phrases.aspect_id == "ag"
        assert phrases.hidden.startswith("Something is off")
        assert phrases.known.endswith(" it is.")

    def test_falls_back_on_none_response(self):
        client = DisabledClient()
        s = _basic_secret()
        phrases = generate_aspect_phrases(
            client, s.aspects[0],
            mechanical="Alex is observing in order to gain leverage on Sam.",
            description="Alex watches Sam.",
        )
        # Deterministic fallback bands carry the mechanical truth in
        # progressively more revealing forms.
        assert phrases.hidden  # non-empty
        assert "Alex" in phrases.suspected
        assert "leverage on Sam" in phrases.known

    def test_falls_back_on_invalid_json(self):
        client = MockClient(["not json at all"])
        s = _basic_secret()
        phrases = generate_aspect_phrases(
            client, s.aspects[0],
            mechanical="Alex is observing in order to gain leverage on Sam.",
            description="Alex watches Sam.",
        )
        # The deterministic fallback's "suspected" line starts with
        # "It looks like " — a stable signal that fallback fired.
        assert phrases.suspected.startswith("It looks like")

    def test_falls_back_on_missing_keys(self):
        client = MockClient([json.dumps({"hidden": "x", "glimpsed": "y"})])
        s = _basic_secret()
        phrases = generate_aspect_phrases(
            client, s.aspects[0],
            mechanical="Alex.",
            description="Alex.",
        )
        # Missing keys → fallback used, hidden phrase is deterministic.
        assert phrases.hidden == "Something is off, but nothing concrete shows."

    def test_falls_back_on_empty_string_values(self):
        client = MockClient([json.dumps({
            "hidden": "x", "glimpsed": "y",
            "suspected": "", "known": "z",
        })])
        s = _basic_secret()
        phrases = generate_aspect_phrases(
            client, s.aspects[0],
            mechanical="Alex.",
            description="Alex.",
        )
        # Empty value → fallback fires; known phrase ends with mechanical.
        assert "Alex" in phrases.known


class TestParsePhrasesJson:
    def test_strips_whitespace(self):
        raw = json.dumps({
            "hidden": "  h  ", "glimpsed": "  g  ",
            "suspected": "  s  ", "known": "  k  ",
        })
        p = _parse_phrases_json(raw, "x")
        assert p is not None
        assert p.hidden == "h"
        assert p.known == "k"

    def test_rejects_non_dict_root(self):
        assert _parse_phrases_json(json.dumps(["a", "b"]), "x") is None

    def test_rejects_non_string_values(self):
        raw = json.dumps({"hidden": 1, "glimpsed": "g", "suspected": "s", "known": "k"})
        assert _parse_phrases_json(raw, "x") is None


class TestFallbackPhrases:
    def test_empty_mechanical_yields_empty_phrases(self):
        p = _fallback_aspect_phrases("a1", "")
        assert p.hidden == ""
        assert p.known == ""

    def test_mechanical_round_trips_into_known(self):
        p = _fallback_aspect_phrases("a1", "She watches him.")
        assert p.known == "She watches him."  # period stripped + appended


# --- reformulate_secret --------------------------------------------------


class TestReformulate:
    def test_uses_llm_when_available(self):
        client = MockClient(["A polished version."])
        out = reformulate_secret(
            client,
            description="Original.",
            aspect_phrases={
                "a": AspectPhrases(aspect_id="a", hidden="h", glimpsed="g",
                                   suspected="s", known="k"),
            },
            mechanical="Mechanical fact.",
        )
        assert out == "A polished version."

    def test_falls_back_on_failure(self):
        out = reformulate_secret(
            DisabledClient(),
            description="Original.",
            aspect_phrases={},
            mechanical="Mechanical.",
        )
        assert out == "Original."


class TestNeedsConsistencyPass:
    def test_two_aspects_skips(self):
        s = Secret(
            id="s", category=SecretCategory.AGENDA,
            aspects=[
                AgendaAspect(id="a1", goal=AgendaGoal.GAIN_LEVERAGE,
                             method=AgendaMethod.OBSERVING),
                AgendaAspect(id="a2", goal=AgendaGoal.PROTECT_CHARACTER,
                             method=AgendaMethod.CONFIDING),
            ],
        )
        assert needs_consistency_pass(s) is False

    def test_three_aspects_runs(self):
        s = Secret(
            id="s", category=SecretCategory.AGENDA,
            aspects=[
                AgendaAspect(id=f"a{i}", goal=AgendaGoal.GAIN_LEVERAGE,
                             method=AgendaMethod.OBSERVING)
                for i in range(3)
            ],
        )
        assert needs_consistency_pass(s) is True


# --- initialise_secret end-to-end ----------------------------------------


class TestInitialiseSecret:
    def test_full_pipeline_with_clean_responses(self):
        s = Secret(
            id="s",
            category=SecretCategory.AGENDA,
            aspects=[
                AgendaAspect(id="a1", goal=AgendaGoal.GAIN_LEVERAGE,
                             method=AgendaMethod.OBSERVING, target="rival"),
                AgendaAspect(id="a2", goal=AgendaGoal.SECURE_TRANSFER,
                             method=AgendaMethod.MANIPULATING),
            ],
            memberships=[SecretMembership(
                character_id="player", role=SecretRole.OWNER, exposure=1.0,
            )],
        )
        # 2 aspects → no consistency pass by default.
        client = MockClient([
            "Flavored description.",     # flavor_secret
            _good_aspect_response("a1"),  # phrases for a1
            _good_aspect_response("a2"),  # phrases for a2
        ])
        out = initialise_secret(
            s, cast={"player": "Alex", "rival": "Sam"},
            character_label="Alex", llm_client=client,
        )
        assert out is s  # mutates in place + returns
        assert s.mechanical
        assert s.description == "Flavored description."
        assert set(s.aspect_phrases.keys()) == {"a1", "a2"}
        assert s.aspect_phrases["a1"].suspected.startswith("The shape is clear")

    def test_runs_consistency_pass_with_three_aspects(self):
        s = Secret(
            id="s", category=SecretCategory.AGENDA,
            aspects=[
                AgendaAspect(id=f"a{i}", goal=AgendaGoal.GAIN_LEVERAGE,
                             method=AgendaMethod.OBSERVING)
                for i in range(3)
            ],
            memberships=[SecretMembership(
                character_id="player", role=SecretRole.OWNER, exposure=1.0,
            )],
        )
        client = MockClient([
            "Original description.",
            _good_aspect_response(),
            _good_aspect_response(),
            _good_aspect_response(),
            "Polished description.",
        ])
        initialise_secret(
            s, cast={"player": "Alex"},
            character_label="Alex", llm_client=client,
        )
        assert s.description == "Polished description."
        # 1 flavor + 3 phrase + 1 reformulate = 5 calls
        assert len(client.calls) == 5

    def test_skips_consistency_pass_when_overridden(self):
        s = Secret(
            id="s", category=SecretCategory.AGENDA,
            aspects=[
                AgendaAspect(id=f"a{i}", goal=AgendaGoal.GAIN_LEVERAGE,
                             method=AgendaMethod.OBSERVING)
                for i in range(3)
            ],
            memberships=[SecretMembership(
                character_id="player", role=SecretRole.OWNER, exposure=1.0,
            )],
        )
        client = MockClient([
            "Original description.",
            _good_aspect_response(),
            _good_aspect_response(),
            _good_aspect_response(),
        ])
        initialise_secret(
            s, cast={"player": "Alex"},
            character_label="Alex", llm_client=client,
            run_consistency_pass=False,
        )
        # No reformulate call — only 4 prompts (flavor + 3 aspects).
        assert len(client.calls) == 4

    def test_pure_fallback_when_llm_disabled(self):
        s = _basic_secret()
        out = initialise_secret(
            s, cast={"player": "Alex", "rival": "Sam"},
            character_label="Alex", llm_client=DisabledClient(),
        )
        # Mechanical filled, description = mechanical, phrases use the
        # deterministic fallback.
        assert "Alex" in out.mechanical
        assert "leverage on Sam" in out.mechanical
        assert out.description == out.mechanical
        ag_phrases = out.aspect_phrases["ag"]
        assert ag_phrases.hidden  # non-empty
        assert "leverage" in ag_phrases.known
