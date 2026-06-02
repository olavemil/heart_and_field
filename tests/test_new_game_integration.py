"""Tests for Phase 18D — GameSession.new_game() integration with the
world-genesis pipeline (roster_factory + world_genesis).

Validates that:
- The generated path (roster=None) produces a full squad + secrets.
- The legacy path (roster=dict) still works.
- PlayerCustomisation overrides are applied.
- Master seed determinism holds.
- Save round-trip preserves the generated cast and secrets.
"""

import random

import pytest

from engine.characters import CharacterRole, TierACharacter, TierBCharacter
from engine.placeholders import unresolved_references
from engine.quirks import Quirk, QuirkDomain, QuirkPattern
from engine.save import deserialise, serialise
from engine.session import GameSession, PlayerCustomisation
from engine.stats import StatName, StatTuple


# --- Generated path (roster=None) -----------------------------------------


class TestGeneratedPath:
    def test_player_is_tier_a_with_given_name(self):
        session = GameSession.new_game("Test Player", seed=100)
        player = session.state.characters["player"]
        assert isinstance(player, TierACharacter)
        assert player.name == "Test Player"

    def test_generates_full_squad(self):
        session = GameSession.new_game("Test Player", seed=100)
        chars = session.state.characters
        # Default soccer: 2 GK + 5 DEF + 5 MID + 3 STR + manager + physio + player = 18
        assert len(chars) >= 10  # at least a reasonable squad

    def test_generates_coaching_staff(self):
        session = GameSession.new_game("Test Player", seed=100)
        roles = [c.role for c in session.state.characters.values()]
        assert CharacterRole.MANAGER in roles
        assert CharacterRole.PHYSIO in roles

    def test_generates_secrets(self):
        session = GameSession.new_game("Test Player", seed=100)
        assert len(session.state.secrets) >= 1

    def test_secrets_initialised_with_mechanical(self):
        session = GameSession.new_game("Test Player", seed=100)
        for secret in session.state.secrets.values():
            assert secret.mechanical, (
                f"Secret {secret.id} missing mechanical description"
            )

    def test_unresolved_references_empty(self):
        session = GameSession.new_game("Test Player", seed=100)
        unresolved = unresolved_references(session.state)
        assert unresolved == {}

    def test_player_has_quirks(self):
        session = GameSession.new_game("Test Player", seed=100)
        player = session.state.characters["player"]
        assert isinstance(player, TierACharacter)
        assert len(player.quirks) >= 1

    def test_player_has_varied_stats(self):
        """Generated stats should not all be 0.5 (the old default)."""
        session = GameSession.new_game("Test Player", seed=100)
        player = session.state.characters["player"]
        assert isinstance(player, TierACharacter)
        values = [t.value for t in player.stats.values()]
        # Not all identical — randomisation has been applied.
        assert len(set(round(v, 4) for v in values)) > 1


# --- Legacy path (roster=dict) -------------------------------------------


class TestLegacyPath:
    def test_legacy_roster_injected(self):
        roster = {
            "tm_a": TierBCharacter(
                id="tm_a", name="A", role=CharacterRole.MIDFIELDER,
                stats={s: 0.5 for s in StatName},
            ),
        }
        session = GameSession.new_game("Legacy", seed=1, roster=roster)
        assert "tm_a" in session.state.characters
        assert session.state.characters["tm_a"].name == "A"

    def test_legacy_player_has_flat_stats(self):
        """Legacy path creates a player with flat 0.5 stats."""
        roster = {
            "tm_a": TierBCharacter(
                id="tm_a", name="A", role=CharacterRole.MIDFIELDER,
                stats={s: 0.5 for s in StatName},
            ),
        }
        session = GameSession.new_game("Legacy", seed=1, roster=roster)
        player = session.state.characters["player"]
        assert isinstance(player, TierACharacter)
        for sn, t in player.stats.items():
            assert t.value == 0.5

    def test_legacy_no_secrets_generated(self):
        roster = {
            "tm_a": TierBCharacter(
                id="tm_a", name="A", role=CharacterRole.MIDFIELDER,
                stats={s: 0.5 for s in StatName},
            ),
        }
        session = GameSession.new_game("Legacy", seed=1, roster=roster)
        assert len(session.state.secrets) == 0


# --- PlayerCustomisation --------------------------------------------------


class TestPlayerCustomisation:
    def test_role_override(self):
        cust = PlayerCustomisation(role=CharacterRole.GOALKEEPER)
        session = GameSession.new_game("Custom", seed=1, customisation=cust)
        player = session.state.characters["player"]
        assert player.role == CharacterRole.GOALKEEPER

    def test_quirks_override(self):
        quirks = [Quirk(domain=QuirkDomain.SOCIAL, pattern=QuirkPattern.AVOIDANT)]
        cust = PlayerCustomisation(quirks=quirks)
        session = GameSession.new_game("Custom", seed=1, customisation=cust)
        player = session.state.characters["player"]
        assert len(player.quirks) == 1
        assert player.quirks[0].domain == QuirkDomain.SOCIAL

    def test_stats_override(self):
        cust = PlayerCustomisation(
            stats={StatName.SPEED: 0.9, StatName.STAMINA: 0.8}
        )
        session = GameSession.new_game("Custom", seed=1, customisation=cust)
        player = session.state.characters["player"]
        assert isinstance(player, TierACharacter)
        assert player.stats[StatName.SPEED].value == 0.9
        assert player.stats[StatName.STAMINA].value == 0.8

    def test_role_override_on_legacy_path(self):
        roster = {
            "tm_a": TierBCharacter(
                id="tm_a", name="A", role=CharacterRole.MIDFIELDER,
                stats={s: 0.5 for s in StatName},
            ),
        }
        cust = PlayerCustomisation(role=CharacterRole.DEFENDER)
        session = GameSession.new_game(
            "Custom", seed=1, roster=roster, customisation=cust,
        )
        player = session.state.characters["player"]
        assert player.role == CharacterRole.DEFENDER

    def test_name_uses_player_name_argument(self):
        cust = PlayerCustomisation(name="Ignored Name")
        session = GameSession.new_game("Display Name", seed=1, customisation=cust)
        player = session.state.characters["player"]
        assert player.name == "Display Name"


# --- Determinism -----------------------------------------------------------


class TestDeterminism:
    def test_same_seed_produces_identical_world(self):
        s1 = GameSession.new_game("Alex", seed=42)
        s2 = GameSession.new_game("Alex", seed=42)
        assert set(s1.state.characters.keys()) == set(s2.state.characters.keys())
        assert set(s1.state.secrets.keys()) == set(s2.state.secrets.keys())
        for cid in s1.state.characters:
            assert s1.state.characters[cid].name == s2.state.characters[cid].name

    def test_different_seed_produces_different_world(self):
        s1 = GameSession.new_game("Alex", seed=1)
        s2 = GameSession.new_game("Alex", seed=999)
        # Character ids are slug-based on randomly drawn names.
        ids_1 = set(s1.state.characters.keys()) - {"player"}
        ids_2 = set(s2.state.characters.keys()) - {"player"}
        assert ids_1 != ids_2


# --- Save round-trip -------------------------------------------------------


class TestSaveRoundTrip:
    def test_generated_world_survives_serialise_deserialise(self):
        session = GameSession.new_game("Alex", seed=42)
        blob = session.serialise()
        restored = GameSession.deserialise(blob)

        assert set(restored.state.characters.keys()) == set(
            session.state.characters.keys()
        )
        assert set(restored.state.secrets.keys()) == set(
            session.state.secrets.keys()
        )
        assert set(restored.state.placeholders.keys()) == set(
            session.state.placeholders.keys()
        )

    def test_player_data_preserved(self):
        cust = PlayerCustomisation(role=CharacterRole.DEFENDER)
        session = GameSession.new_game("Alex", seed=42, customisation=cust)
        blob = session.serialise()
        restored = GameSession.deserialise(blob)

        player = restored.state.characters["player"]
        assert isinstance(player, TierACharacter)
        assert player.name == "Alex"
        assert player.role == CharacterRole.DEFENDER

    def test_secrets_mechanical_preserved(self):
        session = GameSession.new_game("Alex", seed=42)
        blob = session.serialise()
        restored = GameSession.deserialise(blob)

        for sid in session.state.secrets:
            assert (
                restored.state.secrets[sid].mechanical
                == session.state.secrets[sid].mechanical
            )
