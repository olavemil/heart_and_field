"""Tests for the secret system data model (engine.secrets, Phase 13)."""

import pytest

from engine.secrets import (
    AgendaAspect,
    AgendaGoal,
    AgendaMethod,
    AspectPhrases,
    AspectType,
    ExposureBand,
    HistoryAspect,
    HistoryEventType,
    IdentityAspect,
    MetaSecret,
    RelationType,
    RelationshipAspect,
    Secret,
    SecretCategory,
    SecretMembership,
    SecretRelation,
    SecretRelationType,
    SecretRole,
    TabooAspect,
    TabooOrigin,
    TabooSubject,
    aspect_band_for_observer,
    aspect_from_dict,
    aspect_phrase_for_observer,
    exposure_band,
    secret_visible_to,
)


# --- Exposure band thresholds ---------------------------------------------


class TestExposureBand:
    def test_band_cutpoints(self):
        assert exposure_band(0.0) == ExposureBand.HIDDEN
        assert exposure_band(0.19) == ExposureBand.HIDDEN
        assert exposure_band(0.2) == ExposureBand.GLIMPSED
        assert exposure_band(0.49) == ExposureBand.GLIMPSED
        assert exposure_band(0.5) == ExposureBand.SUSPECTED
        assert exposure_band(0.79) == ExposureBand.SUSPECTED
        assert exposure_band(0.8) == ExposureBand.KNOWN
        assert exposure_band(1.0) == ExposureBand.KNOWN

    def test_band_clamps_out_of_range(self):
        assert exposure_band(-0.5) == ExposureBand.HIDDEN
        assert exposure_band(1.5) == ExposureBand.KNOWN


# --- AspectPhrases ---------------------------------------------------------


class TestAspectPhrases:
    def test_by_band_attribute_lookup(self):
        p = AspectPhrases(
            aspect_id="a1",
            hidden="something off",
            glimpsed="patterns emerge",
            suspected="shape is clear",
            known="full picture",
        )
        assert p.by_band(ExposureBand.HIDDEN) == "something off"
        assert p.by_band(ExposureBand.GLIMPSED) == "patterns emerge"
        assert p.by_band(ExposureBand.SUSPECTED) == "shape is clear"
        assert p.by_band(ExposureBand.KNOWN) == "full picture"

    def test_round_trip(self):
        p = AspectPhrases(aspect_id="a", hidden="h", glimpsed="g", suspected="s", known="k")
        assert AspectPhrases.from_dict(p.to_dict()).to_dict() == p.to_dict()


# --- Aspect polymorphism --------------------------------------------------


class TestAspects:
    def test_relationship_round_trip(self):
        a = RelationshipAspect(
            id="rel",
            relation=RelationType.FORMER_LOVER,
            target="char_x",
            mutual=True,
        )
        assert aspect_from_dict(a.to_dict()) == a

    def test_agenda_round_trip(self):
        a = AgendaAspect(
            id="ag",
            goal=AgendaGoal.GAIN_LEVERAGE,
            method=AgendaMethod.OBSERVING,
            target="char_y",
        )
        assert aspect_from_dict(a.to_dict()) == a

    def test_taboo_round_trip(self):
        a = TabooAspect(
            id="tb",
            subject=TabooSubject.HEALTH_CONDITION,
            origin=TabooOrigin.SHAME,
            trigger_tags=["medical", "press"],
        )
        assert aspect_from_dict(a.to_dict()) == a

    def test_history_round_trip(self):
        a = HistoryAspect(
            id="hist",
            event_type=HistoryEventType.BETRAYAL,
            shared_with=["char_a"],
            known_to=["char_a", "char_b"],
        )
        assert aspect_from_dict(a.to_dict()) == a

    def test_identity_round_trip(self):
        a = IdentityAspect(id="ident", fact="real first name is Maria")
        assert aspect_from_dict(a.to_dict()) == a

    def test_aspect_type_field_set_correctly(self):
        a = RelationshipAspect(id="r", relation=RelationType.SIBLING)
        assert a.type == AspectType.RELATIONSHIP


# --- Secret structure -----------------------------------------------------


def _basic_secret(**overrides) -> Secret:
    base = dict(
        id="s1",
        category=SecretCategory.AGENDA,
        aspects=[
            AgendaAspect(
                id="a1",
                goal=AgendaGoal.GAIN_LEVERAGE,
                method=AgendaMethod.OBSERVING,
            )
        ],
        memberships=[
            SecretMembership(
                character_id="player",
                role=SecretRole.OWNER,
                exposure=1.0,
            ),
        ],
    )
    base.update(overrides)
    return Secret(**base)


class TestSecretLookup:
    def test_membership_for_known_character(self):
        s = _basic_secret()
        m = s.membership_for("player")
        assert m is not None
        assert m.role == SecretRole.OWNER

    def test_membership_for_unknown_character(self):
        s = _basic_secret()
        assert s.membership_for("ghost") is None

    def test_aspect_for_known_id(self):
        s = _basic_secret()
        a = s.aspect_for("a1")
        assert a is not None
        assert isinstance(a, AgendaAspect)

    def test_aspect_for_unknown_id(self):
        s = _basic_secret()
        assert s.aspect_for("a_missing") is None


class TestSecretRoundTrip:
    def test_full_round_trip(self):
        s = Secret(
            id="s1",
            category=SecretCategory.HISTORY,
            aspects=[
                RelationshipAspect(id="rel", relation=RelationType.SIBLING, target="x"),
                HistoryAspect(id="hist", event_type=HistoryEventType.SHARED_LOSS),
            ],
            memberships=[
                SecretMembership(
                    character_id="player",
                    role=SecretRole.OWNER,
                    exposure=0.9,
                    knows_other_members=["sib"],
                ),
                SecretMembership(
                    character_id="sib",
                    role=SecretRole.PARTICIPANT,
                    exposure=0.7,
                ),
            ],
            related_secrets=[
                SecretRelation(
                    other_character_id="rival",
                    other_secret_id="s2",
                    relation_type=SecretRelationType.OPPOSING,
                )
            ],
            unlocks_arcs=["arc.reveal"],
            blocks_arcs=["arc.hide"],
            unlocks_events=["evt.confront"],
            exposure_level=0.3,
            reveal_triggers=["postgame", "vulnerability"],
            reveal_threshold=0.7,
            mechanical="player and sib share a loss",
            description="they both lost their mother in the same year",
            aspect_phrases={
                "rel": AspectPhrases(aspect_id="rel", hidden="h", glimpsed="g",
                                     suspected="s", known="k"),
            },
        )
        d = s.to_dict()
        restored = Secret.from_dict(d)
        assert restored.id == s.id
        assert restored.category == SecretCategory.HISTORY
        assert len(restored.aspects) == 2
        assert isinstance(restored.aspects[0], RelationshipAspect)
        assert isinstance(restored.aspects[1], HistoryAspect)
        assert restored.memberships[0].knows_other_members == ["sib"]
        assert restored.related_secrets[0].relation_type == SecretRelationType.OPPOSING
        assert restored.exposure_level == 0.3
        assert restored.aspect_phrases["rel"].suspected == "s"


class TestMetaSecret:
    def test_meta_secret_round_trip_through_secret(self):
        meta = MetaSecret(
            id="m1",
            base_secret_id="s_other",
            aspects=[
                IdentityAspect(id="i", fact="knows real name"),
            ],
            memberships=[
                SecretMembership(
                    character_id="watcher", role=SecretRole.WITNESS, exposure=0.6,
                ),
            ],
        )
        s = _basic_secret(id="s_aware", meta_secret=meta)
        d = s.to_dict()
        restored = Secret.from_dict(d)
        assert restored.meta_secret is not None
        assert restored.meta_secret.is_meta is True
        assert restored.meta_secret.base_secret_id == "s_other"
        assert isinstance(restored.meta_secret.aspects[0], IdentityAspect)

    def test_meta_secret_must_have_is_meta_true(self):
        meta = MetaSecret(id="m", base_secret_id="b")
        meta.is_meta = False  # invalid state
        with pytest.raises(ValueError):
            _basic_secret(meta_secret=meta)


# --- Observer-perspective reveal ------------------------------------------
#
# Symmetric with engine.quirks.visible_to_observer: same observer-side
# inputs (familiarity float + witnessed_event_tags), different return
# type because secrets carry four ExposureBand levels.


class TestObserverReveal:
    def _secret(self) -> Secret:
        return Secret(
            id="s",
            category=SecretCategory.TABOO,
            aspects=[TabooAspect(
                id="a1",
                subject=TabooSubject.PAST_INCIDENT,
                origin=TabooOrigin.TRAUMA,
            )],
            memberships=[
                SecretMembership(
                    character_id="owner",
                    role=SecretRole.OWNER,
                    exposure=1.0,
                ),
                SecretMembership(
                    character_id="witness",
                    role=SecretRole.WITNESS,
                    exposure=0.6,
                ),
            ],
            exposure_level=0.0,
            reveal_triggers=["vulnerability"],
            reveal_threshold=0.7,
            aspect_phrases={
                "a1": AspectPhrases(
                    aspect_id="a1",
                    hidden="h", glimpsed="g", suspected="s", known="k",
                ),
            },
        )

    def test_owner_sees_at_their_exposure_band(self):
        s = self._secret()
        band = aspect_band_for_observer(s, "a1", observer_id="owner")
        assert band == ExposureBand.KNOWN

    def test_witness_sees_at_their_exposure_band(self):
        s = self._secret()
        band = aspect_band_for_observer(s, "a1", observer_id="witness")
        assert band == ExposureBand.SUSPECTED  # 0.6 → SUSPECTED

    def test_non_member_sees_global_band_by_default(self):
        s = self._secret()
        band = aspect_band_for_observer(s, "a1", observer_id="stranger")
        assert band == ExposureBand.HIDDEN  # exposure_level=0.0

    def test_non_member_with_trigger_tag_gets_one_band_bump(self):
        s = self._secret()
        band = aspect_band_for_observer(
            s, "a1", observer_id="stranger",
            witnessed_event_tags=["vulnerability"],
        )
        assert band == ExposureBand.GLIMPSED  # HIDDEN → GLIMPSED

    def test_non_member_with_familiarity_gets_band_bump(self):
        s = self._secret()
        band = aspect_band_for_observer(
            s, "a1", observer_id="stranger",
            observer_familiarity=0.85,
        )
        assert band == ExposureBand.GLIMPSED

    def test_non_member_capped_at_suspected(self):
        # Boost global to SUSPECTED then trigger another bump — non-members
        # never reach KNOWN through inference alone.
        s = self._secret()
        s.exposure_level = 0.6  # SUSPECTED
        band = aspect_band_for_observer(
            s, "a1", observer_id="stranger",
            witnessed_event_tags=["vulnerability"],
        )
        assert band == ExposureBand.SUSPECTED

    def test_non_member_unrelated_event_no_bump(self):
        s = self._secret()
        band = aspect_band_for_observer(
            s, "a1", observer_id="stranger",
            witnessed_event_tags=["training"],
        )
        assert band == ExposureBand.HIDDEN


class TestAspectPhraseLookup:
    def test_returns_phrase_for_member(self):
        s = Secret(
            id="s", category=SecretCategory.AGENDA,
            aspects=[AgendaAspect(
                id="a1", goal=AgendaGoal.GAIN_LEVERAGE, method=AgendaMethod.OBSERVING,
            )],
            memberships=[
                SecretMembership(
                    character_id="o", role=SecretRole.OWNER, exposure=1.0,
                )
            ],
            aspect_phrases={
                "a1": AspectPhrases(
                    aspect_id="a1", hidden="h", glimpsed="g",
                    suspected="s", known="k",
                ),
            },
        )
        phrase = aspect_phrase_for_observer(s, "a1", observer_id="o")
        assert phrase == "k"

    def test_returns_none_when_band_hidden(self):
        s = Secret(
            id="s", category=SecretCategory.AGENDA,
            aspects=[AgendaAspect(
                id="a1", goal=AgendaGoal.GAIN_LEVERAGE, method=AgendaMethod.OBSERVING,
            )],
            aspect_phrases={
                "a1": AspectPhrases(aspect_id="a1", hidden="h", glimpsed="g",
                                    suspected="s", known="k"),
            },
        )
        phrase = aspect_phrase_for_observer(s, "a1", observer_id="stranger")
        assert phrase is None

    def test_returns_none_when_phrases_not_yet_generated(self):
        # Pre-LLM-pipeline state: aspect_phrases empty, but reveal still runs.
        s = Secret(
            id="s", category=SecretCategory.AGENDA,
            aspects=[AgendaAspect(
                id="a1", goal=AgendaGoal.GAIN_LEVERAGE, method=AgendaMethod.OBSERVING,
            )],
            memberships=[
                SecretMembership(
                    character_id="o", role=SecretRole.OWNER, exposure=1.0,
                ),
            ],
            # aspect_phrases left empty.
        )
        phrase = aspect_phrase_for_observer(s, "a1", observer_id="o")
        assert phrase is None

    def test_returns_none_for_unknown_aspect(self):
        s = Secret(id="s", category=SecretCategory.AGENDA)
        phrase = aspect_phrase_for_observer(s, "missing", observer_id="o")
        assert phrase is None


class TestSecretVisibleTo:
    def test_visible_with_phrase(self):
        s = Secret(
            id="s", category=SecretCategory.AGENDA,
            aspects=[AgendaAspect(
                id="a1", goal=AgendaGoal.GAIN_LEVERAGE, method=AgendaMethod.OBSERVING,
            )],
            memberships=[
                SecretMembership(
                    character_id="o", role=SecretRole.OWNER, exposure=1.0,
                ),
            ],
            aspect_phrases={
                "a1": AspectPhrases(aspect_id="a1", hidden="h", glimpsed="g",
                                    suspected="s", known="k"),
            },
        )
        visible, phrase = secret_visible_to(s, "o", "a1")
        assert visible is True
        assert phrase == "k"

    def test_invisible_no_phrase(self):
        s = Secret(
            id="s", category=SecretCategory.AGENDA,
            aspects=[AgendaAspect(
                id="a1", goal=AgendaGoal.GAIN_LEVERAGE, method=AgendaMethod.OBSERVING,
            )],
            exposure_level=0.0,
        )
        visible, phrase = secret_visible_to(s, "stranger", "a1")
        assert visible is False
        assert phrase is None
