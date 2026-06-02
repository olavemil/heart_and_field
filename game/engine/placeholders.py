"""Character placeholders (addendum §3.7) — Phase 15.

When a secret references a character who doesn't yet exist in the
cast, an aspect can carry a *placeholder id* — a stable string that
the world later binds to a real :class:`TierBCharacter` when the
character's introduction event fires.

The placeholder id is stable from the moment the secret is composed.
Aspects keep referencing it; ``compose_mechanical_description`` shows
the id as the name when no cast mapping is provided (visible in dev).
Once :func:`resolve_placeholder` runs, a ``TierBCharacter`` exists with
the same id, so every existing aspect reference resolves naturally —
no rewriting needed.

Scheduling:

- ``scheduling_priority`` lets the planner pick which placeholders to
  introduce next (higher = sooner).
- ``introduction_event_tags`` are event tags that, when seen, signal
  this placeholder can plausibly be introduced (e.g. a ``"family"``
  event makes the player's missing sibling fair game).
- ``due_placeholders(state, *, witnessed_event_tags)`` returns the
  ordered, ready-to-introduce placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Mapping

from .characters import CharacterRole, TierBCharacter
from .secrets import (
    HistoryAspect,
    RelationType,
    RelationshipAspect,
    Secret,
)
from .stats import StatName

if TYPE_CHECKING:
    from .events import GameState


# ===========================================================================
# CharacterPlaceholder
# ===========================================================================


@dataclass
class CharacterPlaceholder:
    """A stable id binding for a character a secret references but the
    world hasn't introduced yet.

    ``required_relation`` is optional — not every placeholder anchors
    to a relationship aspect (some are history co-participants, agenda
    targets, etc.). Authors can still set it to nudge introduction
    flavour. ``introduction_event_tags`` are stringly-typed for now;
    when the addendum's ``EventId`` enum lands in Phase 17 this can
    accept either.
    """

    id: str
    required_role: CharacterRole
    required_relation: RelationType | None = None
    scheduling_priority: float = 0.0
    introduction_event_tags: list[str] = field(default_factory=list)
    secret_ids: list[str] = field(default_factory=list)
    suggested_name: str | None = None  # falls back to id during dev

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "required_role": self.required_role.value,
            "required_relation": (
                self.required_relation.value
                if self.required_relation is not None
                else None
            ),
            "scheduling_priority": self.scheduling_priority,
            "introduction_event_tags": list(self.introduction_event_tags),
            "secret_ids": list(self.secret_ids),
            "suggested_name": self.suggested_name,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "CharacterPlaceholder":
        rel = d.get("required_relation")
        return cls(
            id=str(d["id"]),
            required_role=CharacterRole(d["required_role"]),
            required_relation=RelationType(rel) if rel is not None else None,
            scheduling_priority=float(d.get("scheduling_priority", 0.0)),
            introduction_event_tags=list(d.get("introduction_event_tags", [])),
            secret_ids=list(d.get("secret_ids", [])),
            suggested_name=d.get("suggested_name"),
        )


# ===========================================================================
# Reference discovery
# ===========================================================================


def placeholder_ids_in_secret(secret: Secret) -> set[str]:
    """Return every character id referenced by a secret's aspects.

    Useful for verifying placeholder bookkeeping after edits — every
    referenced id should either be a real character or sit in
    ``state.placeholders``.
    """
    ids: set[str] = set()
    for aspect in secret.aspects:
        if isinstance(aspect, RelationshipAspect):
            if aspect.target:
                ids.add(aspect.target)
        elif isinstance(aspect, HistoryAspect):
            ids.update(aspect.shared_with)
            ids.update(aspect.known_to)
        else:
            target = getattr(aspect, "target", None)
            if isinstance(target, str) and target:
                ids.add(target)
    return ids


def unresolved_references(
    state: "GameState",
) -> dict[str, set[str]]:
    """Map ``placeholder_id -> {secret_id, ...}`` for ids that aren't
    yet bound to a real character.

    Authors can call this after building a world to surface dangling
    references. An id that's neither in ``state.characters`` nor in
    ``state.placeholders`` is a content bug — handled by the caller.
    """
    out: dict[str, set[str]] = {}
    for sid, secret in state.secrets.items():
        for ref_id in placeholder_ids_in_secret(secret):
            if ref_id in state.characters:
                continue
            if ref_id in state.placeholders:
                continue
            out.setdefault(ref_id, set()).add(sid)
    return out


# ===========================================================================
# Resolution
# ===========================================================================


def _default_stats(role: CharacterRole) -> dict[StatName, float]:
    """Mid-line stats for a freshly-resolved placeholder.

    Phase 15 keeps this simple — randomised generation is a separate
    character-creator concern. Authors can post-process via
    ``character_factory`` (see :func:`resolve_placeholder`).
    """
    return {s: 0.5 for s in StatName}


def resolve_placeholder(
    state: "GameState",
    placeholder_id: str,
    *,
    name: str | None = None,
    character_factory=None,
) -> TierBCharacter:
    """Materialise a placeholder into a real :class:`TierBCharacter`.

    The new character takes the placeholder's id, so every existing
    aspect reference (``aspect.target == placeholder_id``) resolves
    correctly without rewriting.

    ``character_factory`` lets callers plug in a richer generator (e.g.
    the random-character creator from Phase 17+); when ``None``, a
    default Tier B with mid-line stats is built. ``name`` overrides the
    placeholder's ``suggested_name``.

    Side effects:
    - Adds the new character to ``state.characters``.
    - Removes the placeholder from ``state.placeholders``.

    Raises ``KeyError`` when the id isn't a known placeholder, and
    ``ValueError`` when a real character already uses that id.
    """
    if placeholder_id not in state.placeholders:
        raise KeyError(f"unknown placeholder id: {placeholder_id!r}")
    if placeholder_id in state.characters:
        raise ValueError(
            f"character id {placeholder_id!r} already exists; cannot "
            f"resolve placeholder onto it"
        )

    placeholder = state.placeholders[placeholder_id]
    label = name or placeholder.suggested_name or placeholder.id

    if character_factory is not None:
        character = character_factory(placeholder, label)
    else:
        character = TierBCharacter(
            id=placeholder.id,
            name=label,
            role=placeholder.required_role,
            stats=_default_stats(placeholder.required_role),
        )

    state.characters[character.id] = character
    del state.placeholders[placeholder_id]
    return character


# ===========================================================================
# Scheduling
# ===========================================================================


def due_placeholders(
    state: "GameState",
    *,
    witnessed_event_tags: Iterable[str] = (),
) -> list[CharacterPlaceholder]:
    """Return placeholders eligible for introduction right now,
    ordered by ``scheduling_priority`` (descending).

    A placeholder is *due* when its ``introduction_event_tags`` is
    empty (introducible at any moment) or overlaps with
    ``witnessed_event_tags``. Empty tags mean "I'm flexible — pick me
    when priority demands it"; non-empty means "I want a thematic
    setup before I show up".
    """
    witnessed = set(witnessed_event_tags)
    eligible: list[CharacterPlaceholder] = []
    for p in state.placeholders.values():
        if not p.introduction_event_tags:
            eligible.append(p)
            continue
        if witnessed & set(p.introduction_event_tags):
            eligible.append(p)
    eligible.sort(key=lambda p: p.scheduling_priority, reverse=True)
    return eligible
