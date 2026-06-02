"""Secret web generator (Phase 18C).

Takes a cast of characters and generates a web of interconnected
secrets — relationship links, agendas, taboos, shared histories,
and hidden identity facts. Characters referenced by aspects who
don't exist in the cast are registered as
:class:`~engine.placeholders.CharacterPlaceholder` entries so they
can be introduced later via the placeholder pipeline.

Every draw is off an injected ``random.Random`` so a single seed
reproduces an identical secret web.

Usage::

    secrets, placeholders = generate_secret_web(
        rng, characters=roster.by_id(),
    )
    state.secrets = secrets
    state.placeholders = placeholders
    assert not unresolved_references(state)
"""

from __future__ import annotations

import logging
import random as _random
from typing import Mapping

from .characters import Character, CharacterRole, TierACharacter, TierBCharacter
from .llm import LLMClient
from .placeholders import (
    CharacterPlaceholder,
    placeholder_ids_in_secret,
)
from .secret_llm import initialise_secret
from .secrets import (
    AgendaAspect,
    AgendaGoal,
    AgendaMethod,
    AspectType,
    ExposureBand,
    HistoryAspect,
    HistoryEventType,
    IdentityAspect,
    RelationshipAspect,
    RelationType,
    Secret,
    SecretCategory,
    SecretMembership,
    SecretRelation,
    SecretRelationType,
    SecretRole,
    TabooAspect,
    TabooOrigin,
    TabooSubject,
)


log = logging.getLogger(__name__)


# ===========================================================================
# Relation-type classification
# ===========================================================================
#
# "External" relations almost always reference someone not on the team
# roster (family, former lovers, employers). "Internal" relations
# typically link two existing cast members (rivals, teammates).
# Mixed relations flip a coin.


_EXTERNAL_RELATIONS: frozenset[RelationType] = frozenset({
    RelationType.PARENT,
    RelationType.CHILD,
    RelationType.SIBLING,
    RelationType.EMPLOYER,
    RelationType.CREDITOR,
    RelationType.DEBTOR,
})

_INTERNAL_RELATIONS: frozenset[RelationType] = frozenset({
    RelationType.RIVAL,
    RelationType.FORMER_TEAMMATE,
    RelationType.MENTOR,
    RelationType.PROTEGE,
})

# Could go either way — decided per-secret via rng.
_MIXED_RELATIONS: frozenset[RelationType] = frozenset({
    RelationType.FORMER_LOVER,
    RelationType.CURRENT_LOVER,
})


# Mapping from relation type to the role the placeholder should have
# when introduced.
_RELATION_TO_ROLE: dict[RelationType, CharacterRole] = {
    RelationType.PARENT: CharacterRole.FAMILY,
    RelationType.CHILD: CharacterRole.FAMILY,
    RelationType.SIBLING: CharacterRole.FAMILY,
    RelationType.FORMER_LOVER: CharacterRole.OTHER,
    RelationType.CURRENT_LOVER: CharacterRole.OTHER,
    RelationType.MENTOR: CharacterRole.ASSISTANT_COACH,
    RelationType.PROTEGE: CharacterRole.OTHER,
    RelationType.EMPLOYER: CharacterRole.OTHER,
    RelationType.CREDITOR: CharacterRole.OTHER,
    RelationType.DEBTOR: CharacterRole.OTHER,
    RelationType.FORMER_TEAMMATE: CharacterRole.OTHER,
    RelationType.RIVAL: CharacterRole.OTHER,
}


# ===========================================================================
# Identity fact pool
# ===========================================================================

_IDENTITY_FACTS: tuple[str, ...] = (
    "a previous name",
    "their actual age",
    "a dual nationality",
    "an undisclosed medical condition",
    "a family connection to a rival club",
    "a previous career outside sport",
    "an ongoing legal matter",
    "a financial arrangement with an outside party",
)


# ===========================================================================
# Event tag pools for reveal triggers
# ===========================================================================

_RELATIONSHIP_REVEAL_TAGS: tuple[str, ...] = (
    "family", "social", "romantic", "downtime", "celebration",
)

_AGENDA_REVEAL_TAGS: tuple[str, ...] = (
    "conflict", "external_pressure", "training", "postgame",
)

_TABOO_REVEAL_TAGS: tuple[str, ...] = (
    "vulnerability", "conflict", "mentor", "postgame",
)

_HISTORY_REVEAL_TAGS: tuple[str, ...] = (
    "postgame", "celebration", "downtime", "vulnerability",
)

_IDENTITY_REVEAL_TAGS: tuple[str, ...] = (
    "external_pressure", "vulnerability", "conflict",
)


# ===========================================================================
# Helpers
# ===========================================================================


def _pick_others(
    rng: _random.Random,
    characters: dict[str, Character],
    exclude: str,
    count: int = 1,
) -> list[str]:
    """Pick ``count`` character ids from the cast, excluding ``exclude``."""
    pool = [cid for cid in characters if cid != exclude]
    if not pool:
        return []
    return rng.sample(pool, min(count, len(pool)))


def _pick_owner(
    rng: _random.Random,
    characters: dict[str, Character],
    used_owners: set[str],
) -> str:
    """Pick a character id to be the secret's owner, preferring unused
    characters so secrets spread across the cast."""
    unused = [cid for cid in characters if cid not in used_owners]
    if unused:
        return rng.choice(unused)
    return rng.choice(list(characters))


def _make_membership(
    character_id: str,
    role: SecretRole,
    *,
    exposure: float = 0.0,
    knows_others: list[str] | None = None,
) -> SecretMembership:
    return SecretMembership(
        character_id=character_id,
        role=role,
        exposure=exposure,
        knows_other_members=knows_others or [],
    )


# ===========================================================================
# Per-category secret generators
# ===========================================================================
#
# Each returns (Secret, set_of_placeholder_ids_created). The caller
# is responsible for creating the CharacterPlaceholder entries.


def _generate_connection_secret(
    secret_id: str,
    rng: _random.Random,
    characters: dict[str, Character],
    used_owners: set[str],
) -> tuple[Secret, set[str]]:
    """CONNECTION category — a hidden relationship between two people."""
    owner_id = _pick_owner(rng, characters, used_owners)
    relation = rng.choice(list(RelationType))
    placeholder_ids: set[str] = set()

    # Decide whether the target is internal or external.
    if relation in _EXTERNAL_RELATIONS:
        use_external = True
    elif relation in _INTERNAL_RELATIONS:
        use_external = False
    else:
        # Mixed — coin flip, leaning external.
        use_external = rng.random() < 0.6

    if use_external:
        target_id = f"ph_{secret_id}_target"
        placeholder_ids.add(target_id)
    else:
        others = _pick_others(rng, characters, owner_id)
        if others:
            target_id = others[0]
        else:
            target_id = f"ph_{secret_id}_target"
            placeholder_ids.add(target_id)

    aspect = RelationshipAspect(
        id=f"{secret_id}_rel",
        relation=relation,
        target=target_id,
        mutual=rng.random() < 0.4,
    )

    reveal_tags = list(rng.sample(
        _RELATIONSHIP_REVEAL_TAGS,
        min(2, len(_RELATIONSHIP_REVEAL_TAGS)),
    ))

    memberships = [
        _make_membership(owner_id, SecretRole.OWNER, exposure=1.0),
    ]
    # If target is internal, make them a participant.
    if target_id not in placeholder_ids:
        memberships.append(
            _make_membership(
                target_id,
                SecretRole.PARTICIPANT,
                exposure=0.8 if aspect.mutual else 0.0,
                knows_others=[owner_id] if aspect.mutual else [],
            ),
        )

    return Secret(
        id=secret_id,
        category=SecretCategory.CONNECTION,
        aspects=[aspect],
        memberships=memberships,
        reveal_triggers=reveal_tags,
    ), placeholder_ids


def _generate_agenda_secret(
    secret_id: str,
    rng: _random.Random,
    characters: dict[str, Character],
    used_owners: set[str],
) -> tuple[Secret, set[str]]:
    """AGENDA category — a hidden goal pursued through a method."""
    owner_id = _pick_owner(rng, characters, used_owners)
    goal = rng.choice(list(AgendaGoal))
    method = rng.choice(list(AgendaMethod))
    placeholder_ids: set[str] = set()

    # Goals that target someone.
    _TARGETED_GOALS = {
        AgendaGoal.PROTECT_CHARACTER,
        AgendaGoal.EXPOSE_CHARACTER,
        AgendaGoal.SABOTAGE_CHARACTER,
    }
    target_id: str | None = None
    if goal in _TARGETED_GOALS:
        others = _pick_others(rng, characters, owner_id)
        if others:
            target_id = others[0]

    aspect = AgendaAspect(
        id=f"{secret_id}_agenda",
        goal=goal,
        method=method,
        target=target_id,
    )

    reveal_tags = list(rng.sample(
        _AGENDA_REVEAL_TAGS,
        min(2, len(_AGENDA_REVEAL_TAGS)),
    ))

    memberships = [
        _make_membership(owner_id, SecretRole.OWNER, exposure=1.0),
    ]
    # Maybe a witness who suspects something.
    if rng.random() < 0.3:
        witnesses = _pick_others(rng, characters, owner_id)
        if witnesses:
            memberships.append(
                _make_membership(witnesses[0], SecretRole.WITNESS, exposure=0.3),
            )

    return Secret(
        id=secret_id,
        category=SecretCategory.AGENDA,
        aspects=[aspect],
        memberships=memberships,
        reveal_triggers=reveal_tags,
    ), placeholder_ids


def _generate_taboo_secret(
    secret_id: str,
    rng: _random.Random,
    characters: dict[str, Character],
    used_owners: set[str],
) -> tuple[Secret, set[str]]:
    """TABOO category — a subject the owner won't discuss."""
    owner_id = _pick_owner(rng, characters, used_owners)
    subject = rng.choice(list(TabooSubject))
    origin = rng.choice(list(TabooOrigin))

    aspect = TabooAspect(
        id=f"{secret_id}_taboo",
        subject=subject,
        origin=origin,
        trigger_tags=list(rng.sample(
            _TABOO_REVEAL_TAGS,
            min(2, len(_TABOO_REVEAL_TAGS)),
        )),
    )

    reveal_tags = list(rng.sample(
        _TABOO_REVEAL_TAGS,
        min(2, len(_TABOO_REVEAL_TAGS)),
    ))

    return Secret(
        id=secret_id,
        category=SecretCategory.TABOO,
        aspects=[aspect],
        memberships=[
            _make_membership(owner_id, SecretRole.OWNER, exposure=1.0),
        ],
        reveal_triggers=reveal_tags,
    ), set()


def _generate_history_secret(
    secret_id: str,
    rng: _random.Random,
    characters: dict[str, Character],
    used_owners: set[str],
) -> tuple[Secret, set[str]]:
    """HISTORY category — a shared past event between characters."""
    owner_id = _pick_owner(rng, characters, used_owners)
    event_type = rng.choice(list(HistoryEventType))
    placeholder_ids: set[str] = set()

    # Pick 1–2 people who share this history.
    share_count = rng.randint(1, 2)
    shared_with: list[str] = []
    others = _pick_others(rng, characters, owner_id, count=share_count)
    if others:
        shared_with.extend(others)
    else:
        # No cast members available — create a placeholder.
        ph_id = f"ph_{secret_id}_shared"
        placeholder_ids.add(ph_id)
        shared_with.append(ph_id)

    # Maybe someone else knows about it.
    known_to: list[str] = []
    if rng.random() < 0.3:
        exclude = {owner_id} | set(shared_with)
        pool = [cid for cid in characters if cid not in exclude]
        if pool:
            known_to.append(rng.choice(pool))

    aspect = HistoryAspect(
        id=f"{secret_id}_history",
        event_type=event_type,
        shared_with=shared_with,
        known_to=known_to,
    )

    reveal_tags = list(rng.sample(
        _HISTORY_REVEAL_TAGS,
        min(2, len(_HISTORY_REVEAL_TAGS)),
    ))

    memberships = [
        _make_membership(owner_id, SecretRole.OWNER, exposure=1.0),
    ]
    for cid in shared_with:
        if cid not in placeholder_ids:
            memberships.append(
                _make_membership(
                    cid, SecretRole.PARTICIPANT,
                    exposure=0.8,
                    knows_others=[owner_id],
                ),
            )
    for cid in known_to:
        memberships.append(
            _make_membership(cid, SecretRole.WITNESS, exposure=0.5),
        )

    return Secret(
        id=secret_id,
        category=SecretCategory.HISTORY,
        aspects=[aspect],
        memberships=memberships,
        reveal_triggers=reveal_tags,
    ), placeholder_ids


def _generate_identity_secret(
    secret_id: str,
    rng: _random.Random,
    characters: dict[str, Character],
    used_owners: set[str],
) -> tuple[Secret, set[str]]:
    """IDENTITY category — a concealed fact about the owner."""
    owner_id = _pick_owner(rng, characters, used_owners)
    fact = rng.choice(_IDENTITY_FACTS)

    aspect = IdentityAspect(
        id=f"{secret_id}_identity",
        fact=fact,
    )

    reveal_tags = list(rng.sample(
        _IDENTITY_REVEAL_TAGS,
        min(2, len(_IDENTITY_REVEAL_TAGS)),
    ))

    memberships = [
        _make_membership(owner_id, SecretRole.OWNER, exposure=1.0),
    ]
    # Maybe someone suspects.
    if rng.random() < 0.25:
        suspects = _pick_others(rng, characters, owner_id)
        if suspects:
            memberships.append(
                _make_membership(suspects[0], SecretRole.SUSPECT, exposure=0.2),
            )

    return Secret(
        id=secret_id,
        category=SecretCategory.IDENTITY,
        aspects=[aspect],
        memberships=memberships,
        reveal_triggers=reveal_tags,
    ), set()


_CATEGORY_GENERATORS = {
    SecretCategory.CONNECTION: _generate_connection_secret,
    SecretCategory.AGENDA: _generate_agenda_secret,
    SecretCategory.TABOO: _generate_taboo_secret,
    SecretCategory.HISTORY: _generate_history_secret,
    SecretCategory.IDENTITY: _generate_identity_secret,
}


# ===========================================================================
# Cross-secret relations
# ===========================================================================


def _link_shared_character_secrets(
    secrets: dict[str, Secret],
) -> None:
    """Add ``SecretRelation`` cross-references between secrets that
    share a character membership. Mutates secrets in place."""
    char_to_secrets: dict[str, list[str]] = {}
    for sid, secret in secrets.items():
        for m in secret.memberships:
            char_to_secrets.setdefault(m.character_id, []).append(sid)

    for cid, sids in char_to_secrets.items():
        if len(sids) < 2:
            continue
        for i, sid_a in enumerate(sids):
            for sid_b in sids[i + 1:]:
                secrets[sid_a].related_secrets.append(
                    SecretRelation(
                        other_character_id=cid,
                        other_secret_id=sid_b,
                        relation_type=SecretRelationType.SHARED,
                    )
                )
                secrets[sid_b].related_secrets.append(
                    SecretRelation(
                        other_character_id=cid,
                        other_secret_id=sid_a,
                        relation_type=SecretRelationType.SHARED,
                    )
                )


# ===========================================================================
# Placeholder builder
# ===========================================================================


def _build_placeholders(
    secrets: dict[str, Secret],
    characters: dict[str, Character],
    placeholder_ids_by_secret: dict[str, set[str]],
) -> dict[str, CharacterPlaceholder]:
    """Create :class:`CharacterPlaceholder` entries for every id that
    appears in aspects but isn't in the cast."""
    placeholders: dict[str, CharacterPlaceholder] = {}

    for sid, ph_ids in placeholder_ids_by_secret.items():
        secret = secrets[sid]
        for ph_id in ph_ids:
            if ph_id in characters or ph_id in placeholders:
                continue

            # Try to infer role and relation from the aspect.
            required_role = CharacterRole.OTHER
            required_relation: RelationType | None = None
            for aspect in secret.aspects:
                if isinstance(aspect, RelationshipAspect) and aspect.target == ph_id:
                    required_relation = aspect.relation
                    required_role = _RELATION_TO_ROLE.get(
                        aspect.relation, CharacterRole.OTHER
                    )
                    break

            # Collect all secrets that reference this placeholder.
            secret_ids = [
                s_id for s_id, s in secrets.items()
                if ph_id in placeholder_ids_in_secret(s)
            ]

            placeholders[ph_id] = CharacterPlaceholder(
                id=ph_id,
                required_role=required_role,
                required_relation=required_relation,
                scheduling_priority=0.5,
                introduction_event_tags=list(secret.reveal_triggers),
                secret_ids=secret_ids,
            )

    return placeholders


# ===========================================================================
# Public API
# ===========================================================================


def _build_cast_map(characters: dict[str, Character]) -> dict[str, str]:
    """Build the ``{id: display_name}`` map that the LLM pipeline needs."""
    return {cid: c.name for cid, c in characters.items()}


def generate_secret_web(
    rng: _random.Random,
    *,
    characters: dict[str, Character],
    secret_count_range: tuple[int, int] = (3, 6),
    llm_client: LLMClient | None = None,
    character_label: str = "",
) -> tuple[dict[str, Secret], dict[str, CharacterPlaceholder]]:
    """Generate a web of interconnected secrets across the cast.

    Returns ``(secrets, placeholders)`` ready to be assigned to
    ``GameState.secrets`` and ``GameState.placeholders``.

    ``llm_client`` is passed through to
    :func:`~engine.secret_llm.initialise_secret`. When ``None`` a
    disabled client is used — the pipeline produces deterministic
    mechanical descriptions and fallback phrases so the result is
    always playable.

    ``character_label`` is a human-readable description of the focal
    character used as LLM grounding (e.g.
    ``"Player — striker, mid-twenties"``).
    """
    low, high = secret_count_range
    count = rng.randint(low, high)

    categories = list(SecretCategory)
    used_owners: set[str] = set()
    secrets: dict[str, Secret] = {}
    all_placeholder_ids: dict[str, set[str]] = {}

    for i in range(count):
        category = rng.choice(categories)
        secret_id = f"secret_{i}"
        generator = _CATEGORY_GENERATORS[category]
        secret, ph_ids = generator(secret_id, rng, characters, used_owners)
        secrets[secret_id] = secret
        all_placeholder_ids[secret_id] = ph_ids

        # Track owners for spread.
        for m in secret.memberships:
            if m.role == SecretRole.OWNER:
                used_owners.add(m.character_id)

    # Wire cross-secret relations for characters appearing in multiple secrets.
    _link_shared_character_secrets(secrets)

    # Build placeholder entries for unbound targets.
    placeholders = _build_placeholders(secrets, characters, all_placeholder_ids)

    # Initialise each secret through the LLM pipeline (or fallback).
    client = llm_client if llm_client is not None else LLMClient(enabled=False)
    cast_map = _build_cast_map(characters)
    for secret in secrets.values():
        initialise_secret(
            secret,
            cast=cast_map,
            character_label=character_label or "an athlete",
            llm_client=client,
        )

    return secrets, placeholders
