"""Tests for the secret web generator (engine.world_genesis, Phase 18C).

Validates that ``generate_secret_web`` produces a coherent set of
secrets + placeholders where every character reference is accounted
for, ``initialise_secret`` runs on each, and the results round-trip
through ``GameState`` and ``unresolved_references``.
"""

import random

import pytest

from engine.characters import CharacterRole, TierACharacter, TierBCharacter
from engine.events import GameState
from engine.llm import LLMClient, LLMPrompt
from engine.placeholders import (
    CharacterPlaceholder,
    placeholder_ids_in_secret,
    unresolved_references,
)
from engine.secrets import (
    AgendaAspect,
    AspectType,
    HistoryAspect,
    IdentityAspect,
    RelationshipAspect,
    Secret,
    SecretCategory,
    SecretMembership,
    SecretRole,
    TabooAspect,
)
from engine.stats import StatName
from engine.world_genesis import (
    _build_cast_map,
    _build_placeholders,
    _generate_agenda_secret,
    _generate_connection_secret,
    _generate_history_secret,
    _generate_identity_secret,
    _generate_taboo_secret,
    _link_shared_character_secrets,
    generate_secret_web,
)


# --- Helpers --------------------------------------------------------------


def _make_roster(count: int = 5) -> dict[str, TierBCharacter]:
    """Create a minimal cast of ``count`` Tier B characters."""
    chars: dict[str, TierBCharacter] = {}
    for i in range(count):
        cid = f"char_{i}"
        chars[cid] = TierBCharacter(
            id=cid,
            name=f"Character {i}",
            role=CharacterRole.MIDFIELDER,
            stats={s: 0.5 for s in StatName},
        )
    return chars


def _make_state_with(
    characters: dict[str, TierBCharacter],
    secrets: dict[str, Secret],
    placeholders: dict[str, CharacterPlaceholder],
) -> GameState:
    return GameState(
        characters=dict(characters),
        secrets=dict(secrets),
        placeholders=dict(placeholders),
    )


class DisabledClient:
    """Duck-type LLMClient that always returns None."""

    def generate(self, prompt: LLMPrompt):
        return None


class CountingClient:
    """Duck-type LLMClient that counts calls and returns None."""

    def __init__(self):
        self.call_count = 0

    def generate(self, prompt: LLMPrompt):
        self.call_count += 1
        return None


# --- generate_secret_web (integration) -----------------------------------


class TestGenerateSecretWeb:
    def test_returns_dicts(self):
        rng = random.Random(42)
        chars = _make_roster(5)
        secrets, placeholders = generate_secret_web(
            rng, characters=chars, secret_count_range=(3, 3),
        )
        assert isinstance(secrets, dict)
        assert isinstance(placeholders, dict)
        assert len(secrets) == 3

    def test_secret_count_within_range(self):
        rng = random.Random(99)
        chars = _make_roster(5)
        secrets, _ = generate_secret_web(
            rng, characters=chars, secret_count_range=(2, 8),
        )
        assert 2 <= len(secrets) <= 8

    def test_every_secret_has_at_least_one_membership(self):
        rng = random.Random(7)
        chars = _make_roster(5)
        secrets, _ = generate_secret_web(
            rng, characters=chars, secret_count_range=(4, 4),
        )
        for secret in secrets.values():
            assert len(secret.memberships) >= 1

    def test_every_secret_has_at_least_one_aspect(self):
        rng = random.Random(11)
        chars = _make_roster(5)
        secrets, _ = generate_secret_web(
            rng, characters=chars, secret_count_range=(4, 4),
        )
        for secret in secrets.values():
            assert len(secret.aspects) >= 1

    def test_secrets_reference_real_characters_where_possible(self):
        rng = random.Random(42)
        chars = _make_roster(10)
        secrets, _ = generate_secret_web(
            rng, characters=chars, secret_count_range=(5, 5),
        )
        # At least some memberships reference real characters.
        real_refs = 0
        for secret in secrets.values():
            for m in secret.memberships:
                if m.character_id in chars:
                    real_refs += 1
        assert real_refs >= 5  # at least one owner per secret

    def test_unresolved_references_empty_after_bookkeeping(self):
        """Every character id referenced by aspects is either a real
        character or a registered placeholder."""
        rng = random.Random(123)
        chars = _make_roster(5)
        secrets, placeholders = generate_secret_web(
            rng, characters=chars, secret_count_range=(5, 5),
        )
        state = _make_state_with(chars, secrets, placeholders)
        unresolved = unresolved_references(state)
        assert unresolved == {}, (
            f"Dangling references: {unresolved}"
        )

    def test_determinism_under_same_seed(self):
        chars = _make_roster(5)
        secrets_a, ph_a = generate_secret_web(
            random.Random(42), characters=chars, secret_count_range=(4, 4),
        )
        secrets_b, ph_b = generate_secret_web(
            random.Random(42), characters=chars, secret_count_range=(4, 4),
        )
        assert list(secrets_a.keys()) == list(secrets_b.keys())
        assert list(ph_a.keys()) == list(ph_b.keys())
        for sid in secrets_a:
            assert secrets_a[sid].category == secrets_b[sid].category

    def test_different_seed_produces_different_secrets(self):
        chars = _make_roster(10)
        secrets_a, _ = generate_secret_web(
            random.Random(1), characters=chars, secret_count_range=(5, 5),
        )
        secrets_b, _ = generate_secret_web(
            random.Random(999), characters=chars, secret_count_range=(5, 5),
        )
        categories_a = [s.category for s in secrets_a.values()]
        categories_b = [s.category for s in secrets_b.values()]
        # With 5 secrets from 5 categories, different seeds should
        # produce different category sequences most of the time.
        # If they happen to match, at least the memberships will differ.
        if categories_a == categories_b:
            owners_a = {
                sid: [m.character_id for m in s.memberships]
                for sid, s in secrets_a.items()
            }
            owners_b = {
                sid: [m.character_id for m in s.memberships]
                for sid, s in secrets_b.items()
            }
            assert owners_a != owners_b

    def test_initialise_secret_runs_on_each(self):
        """After generation, every secret has a non-empty mechanical
        description (proving ``initialise_secret`` was called)."""
        rng = random.Random(7)
        chars = _make_roster(5)
        secrets, _ = generate_secret_web(
            rng, characters=chars, secret_count_range=(3, 3),
        )
        for secret in secrets.values():
            assert secret.mechanical, (
                f"Secret {secret.id} has empty mechanical — "
                f"initialise_secret was not called"
            )

    def test_initialise_secret_called_once_per_secret(self):
        """Counting client tracks that the LLM pipeline was invoked
        once per secret (flavor call)."""
        rng = random.Random(7)
        chars = _make_roster(5)
        client = CountingClient()
        secrets, _ = generate_secret_web(
            rng,
            characters=chars,
            secret_count_range=(3, 3),
            llm_client=client,
        )
        # Each secret triggers at least one LLM call (flavor).
        # With 1 aspect per secret: 1 flavor + 1 aspect_phrases = 2 calls each.
        assert client.call_count >= len(secrets)

    def test_no_llm_client_uses_fallback(self):
        """When no LLM client is provided, secrets still initialise
        with deterministic mechanical descriptions."""
        rng = random.Random(42)
        chars = _make_roster(5)
        secrets, _ = generate_secret_web(
            rng, characters=chars, secret_count_range=(3, 3),
            llm_client=None,
        )
        for secret in secrets.values():
            assert secret.mechanical

    def test_placeholders_track_secret_ids(self):
        """Each placeholder records which secrets reference it."""
        rng = random.Random(42)
        chars = _make_roster(3)
        secrets, placeholders = generate_secret_web(
            rng, characters=chars, secret_count_range=(6, 6),
        )
        for ph in placeholders.values():
            assert len(ph.secret_ids) >= 1
            for sid in ph.secret_ids:
                assert sid in secrets

    def test_owners_spread_across_cast(self):
        """When the cast is larger than the secret count, owners should
        spread rather than clustering on one character."""
        rng = random.Random(42)
        chars = _make_roster(10)
        secrets, _ = generate_secret_web(
            rng, characters=chars, secret_count_range=(5, 5),
        )
        owners = set()
        for secret in secrets.values():
            for m in secret.memberships:
                if m.role == SecretRole.OWNER:
                    owners.add(m.character_id)
        # With 10 characters and 5 secrets, expect at least 3 distinct owners.
        assert len(owners) >= 3


# --- Per-category generators ---------------------------------------------


class TestConnectionSecret:
    def test_has_relationship_aspect(self):
        rng = random.Random(42)
        chars = _make_roster(5)
        secret, _ = _generate_connection_secret("s0", rng, chars, set())
        assert secret.category == SecretCategory.CONNECTION
        assert any(isinstance(a, RelationshipAspect) for a in secret.aspects)

    def test_external_relation_creates_placeholder(self):
        """Force an external relation type and verify a placeholder id
        is returned."""
        # Run many seeds until we get an external relation.
        for seed in range(100):
            rng = random.Random(seed)
            chars = _make_roster(5)
            secret, ph_ids = _generate_connection_secret("s0", rng, chars, set())
            rel = secret.aspects[0]
            assert isinstance(rel, RelationshipAspect)
            if ph_ids:
                # The placeholder id should match the aspect target.
                assert rel.target in ph_ids
                return
        pytest.skip("No external relation generated in 100 seeds")

    def test_internal_relation_uses_cast(self):
        for seed in range(100):
            rng = random.Random(seed)
            chars = _make_roster(5)
            secret, ph_ids = _generate_connection_secret("s0", rng, chars, set())
            rel = secret.aspects[0]
            assert isinstance(rel, RelationshipAspect)
            if not ph_ids and rel.target in chars:
                return
        pytest.skip("No internal relation generated in 100 seeds")


class TestAgendaSecret:
    def test_has_agenda_aspect(self):
        rng = random.Random(42)
        chars = _make_roster(5)
        secret, _ = _generate_agenda_secret("s0", rng, chars, set())
        assert secret.category == SecretCategory.AGENDA
        assert any(isinstance(a, AgendaAspect) for a in secret.aspects)

    def test_no_placeholders(self):
        """Agenda secrets target existing cast members — no placeholders."""
        rng = random.Random(42)
        chars = _make_roster(5)
        _, ph_ids = _generate_agenda_secret("s0", rng, chars, set())
        assert ph_ids == set()


class TestTabooSecret:
    def test_has_taboo_aspect(self):
        rng = random.Random(42)
        chars = _make_roster(5)
        secret, _ = _generate_taboo_secret("s0", rng, chars, set())
        assert secret.category == SecretCategory.TABOO
        assert any(isinstance(a, TabooAspect) for a in secret.aspects)

    def test_no_placeholders(self):
        rng = random.Random(42)
        chars = _make_roster(5)
        _, ph_ids = _generate_taboo_secret("s0", rng, chars, set())
        assert ph_ids == set()


class TestHistorySecret:
    def test_has_history_aspect(self):
        rng = random.Random(42)
        chars = _make_roster(5)
        secret, _ = _generate_history_secret("s0", rng, chars, set())
        assert secret.category == SecretCategory.HISTORY
        assert any(isinstance(a, HistoryAspect) for a in secret.aspects)

    def test_shared_with_is_populated(self):
        rng = random.Random(42)
        chars = _make_roster(5)
        secret, _ = _generate_history_secret("s0", rng, chars, set())
        hist = secret.aspects[0]
        assert isinstance(hist, HistoryAspect)
        assert len(hist.shared_with) >= 1


class TestIdentitySecret:
    def test_has_identity_aspect(self):
        rng = random.Random(42)
        chars = _make_roster(5)
        secret, _ = _generate_identity_secret("s0", rng, chars, set())
        assert secret.category == SecretCategory.IDENTITY
        assert any(isinstance(a, IdentityAspect) for a in secret.aspects)

    def test_no_placeholders(self):
        rng = random.Random(42)
        chars = _make_roster(5)
        _, ph_ids = _generate_identity_secret("s0", rng, chars, set())
        assert ph_ids == set()


# --- Cross-secret linking -------------------------------------------------


class TestCrossSecretLinks:
    def test_shared_character_creates_relations(self):
        owner = "char_0"
        s1 = Secret(
            id="s1",
            category=SecretCategory.TABOO,
            memberships=[SecretMembership(character_id=owner, role=SecretRole.OWNER)],
        )
        s2 = Secret(
            id="s2",
            category=SecretCategory.IDENTITY,
            memberships=[SecretMembership(character_id=owner, role=SecretRole.OWNER)],
        )
        secrets = {"s1": s1, "s2": s2}
        _link_shared_character_secrets(secrets)
        # Both secrets should cross-reference each other.
        assert len(s1.related_secrets) == 1
        assert s1.related_secrets[0].other_secret_id == "s2"
        assert len(s2.related_secrets) == 1
        assert s2.related_secrets[0].other_secret_id == "s1"

    def test_no_link_when_no_shared_character(self):
        s1 = Secret(
            id="s1",
            category=SecretCategory.TABOO,
            memberships=[SecretMembership(character_id="c1", role=SecretRole.OWNER)],
        )
        s2 = Secret(
            id="s2",
            category=SecretCategory.TABOO,
            memberships=[SecretMembership(character_id="c2", role=SecretRole.OWNER)],
        )
        secrets = {"s1": s1, "s2": s2}
        _link_shared_character_secrets(secrets)
        assert len(s1.related_secrets) == 0
        assert len(s2.related_secrets) == 0


# --- Placeholder builder --------------------------------------------------


class TestBuildPlaceholders:
    def test_creates_placeholder_for_unbound_target(self):
        secret = Secret(
            id="s0",
            category=SecretCategory.CONNECTION,
            aspects=[RelationshipAspect(
                id="s0_rel",
                relation=RelationshipAspect.__dataclass_fields__["relation"].default
                if hasattr(RelationshipAspect.__dataclass_fields__["relation"], "default")
                else __import__("engine.secrets", fromlist=["RelationType"]).RelationType.PARENT,
                target="ph_s0_target",
            )],
            memberships=[
                SecretMembership(character_id="char_0", role=SecretRole.OWNER),
            ],
            reveal_triggers=["family"],
        )
        chars = _make_roster(3)
        phs = _build_placeholders(
            {"s0": secret}, chars, {"s0": {"ph_s0_target"}},
        )
        assert "ph_s0_target" in phs
        ph = phs["ph_s0_target"]
        assert ph.id == "ph_s0_target"
        assert len(ph.secret_ids) >= 1

    def test_skips_existing_character(self):
        chars = _make_roster(3)
        secret = Secret(
            id="s0",
            category=SecretCategory.HISTORY,
            aspects=[HistoryAspect(
                id="s0_hist",
                event_type=HistoryAspect.__dataclass_fields__["event_type"].default
                if hasattr(HistoryAspect.__dataclass_fields__["event_type"], "default")
                else __import__("engine.secrets", fromlist=["HistoryEventType"]).HistoryEventType.INCIDENT,
                shared_with=["char_0"],
            )],
            memberships=[
                SecretMembership(character_id="char_1", role=SecretRole.OWNER),
            ],
        )
        phs = _build_placeholders(
            {"s0": secret}, chars, {"s0": set()},
        )
        # char_0 is a real character — no placeholder should be created.
        assert "char_0" not in phs


# --- Cast map builder ----------------------------------------------------


class TestBuildCastMap:
    def test_maps_id_to_name(self):
        chars = _make_roster(3)
        cast_map = _build_cast_map(chars)
        assert cast_map["char_0"] == "Character 0"
        assert cast_map["char_1"] == "Character 1"
        assert len(cast_map) == 3


# --- Save round-trip via GameState ----------------------------------------


class TestSaveRoundTrip:
    def test_generated_web_survives_serialise_deserialise(self):
        from engine.save import deserialise, serialise

        rng = random.Random(42)
        chars = _make_roster(5)
        secrets, placeholders = generate_secret_web(
            rng, characters=chars, secret_count_range=(3, 3),
        )
        state = _make_state_with(chars, secrets, placeholders)

        blob = serialise(state)
        restored, _, _ = deserialise(blob)

        assert set(restored.secrets.keys()) == set(state.secrets.keys())
        assert set(restored.placeholders.keys()) == set(state.placeholders.keys())
        for sid in state.secrets:
            assert restored.secrets[sid].category == state.secrets[sid].category
            assert restored.secrets[sid].mechanical == state.secrets[sid].mechanical

    def test_unresolved_references_empty_after_round_trip(self):
        from engine.save import deserialise, serialise

        rng = random.Random(42)
        chars = _make_roster(5)
        secrets, placeholders = generate_secret_web(
            rng, characters=chars, secret_count_range=(4, 4),
        )
        state = _make_state_with(chars, secrets, placeholders)
        blob = serialise(state)
        restored, _, _ = deserialise(blob)

        unresolved = unresolved_references(restored)
        assert unresolved == {}


# --- Edge cases -----------------------------------------------------------


class TestEdgeCases:
    def test_single_character_cast(self):
        """A cast with one character still produces valid secrets."""
        rng = random.Random(42)
        chars = _make_roster(1)
        secrets, placeholders = generate_secret_web(
            rng, characters=chars, secret_count_range=(2, 2),
        )
        assert len(secrets) == 2
        state = _make_state_with(chars, secrets, placeholders)
        assert unresolved_references(state) == {}

    def test_zero_secret_range(self):
        rng = random.Random(42)
        chars = _make_roster(5)
        secrets, placeholders = generate_secret_web(
            rng, characters=chars, secret_count_range=(0, 0),
        )
        assert len(secrets) == 0
        assert len(placeholders) == 0

    def test_large_secret_count(self):
        rng = random.Random(42)
        chars = _make_roster(8)
        secrets, placeholders = generate_secret_web(
            rng, characters=chars, secret_count_range=(12, 12),
        )
        assert len(secrets) == 12
        state = _make_state_with(chars, secrets, placeholders)
        assert unresolved_references(state) == {}

    def test_all_categories_reachable(self):
        """Over many seeds, all five secret categories appear."""
        seen = set()
        for seed in range(50):
            rng = random.Random(seed)
            chars = _make_roster(5)
            secrets, _ = generate_secret_web(
                rng, characters=chars, secret_count_range=(5, 5),
            )
            for s in secrets.values():
                seen.add(s.category)
        assert seen == set(SecretCategory)
