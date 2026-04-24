"""Authoring helpers shared across blueprint files.

These are thin builders, not engine code. Keep them here so content modules
stay focused on the authored material.
"""

from __future__ import annotations

from engine.characters import Character, CharacterRole, TierACharacter
from engine.events import CastFilter, RoleSlot


def is_player(c: Character) -> bool:
    """True if the character is the player — a Tier A whose id is 'player'."""
    return isinstance(c, TierACharacter) and c.id == "player"


def not_player(c: Character) -> bool:
    return not is_player(c)


def has_role(*roles: CharacterRole) -> CastFilter:
    def _filter(c: Character) -> bool:
        return c.role in roles

    return _filter


def teammate() -> CastFilter:
    """Any character who isn't the manager/media/family."""
    excluded = {
        CharacterRole.MANAGER,
        CharacterRole.MEDIA,
        CharacterRole.FAMILY,
        CharacterRole.OTHER,
    }

    def _filter(c: Character) -> bool:
        return c.role not in excluded

    return _filter
