"""Secret LLM pipeline (addendum §3.6) — Phase 14.

Four short, bounded calls turn a structured secret into authored
narration that the reveal logic in :mod:`engine.secrets` can serve at
each :class:`engine.secrets.ExposureBand`. The pipeline runs once per
secret at character / world initialisation; results are cached on the
``Secret`` itself so play never blocks on the LLM.

Pipeline:

    aspects (structured)
        ↓  compose_mechanical_description()    deterministic, no LLM
    mechanical sentence
        ↓  flavor_secret()                     LLM call 1
    secret description
        ↓  generate_aspect_phrases()           LLM call 2 (per aspect)
    aspect phrase bands
        ↓  reformulate_secret() [optional]     LLM call 3
    final description

Every LLM call is wrapped in graceful fallback: if the client returns
``None`` (LM Studio down, JSON malformed, name validation failed) the
caller substitutes a deterministic fallback so play never sees an
empty string. The Phase 13 reveal logic still works on a pure-fallback
secret — every band reads as a slightly more revealing variant of the
mechanical sentence.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Sequence

from .llm import LLMClient, LLMPrompt
from .secrets import (
    AgendaAspect,
    AspectPhrases,
    AspectType,
    HistoryAspect,
    IdentityAspect,
    RelationshipAspect,
    Secret,
    SecretAspect,
    SecretRole,
    TabooAspect,
)


log = logging.getLogger(__name__)


# ===========================================================================
# Step 1 — deterministic mechanical description
# ===========================================================================


# One canonical mechanical sentence per aspect type. Authors should
# *never* contradict these in flavor / aspect-phrase prompts; the LLM
# rephrases for variety, the mechanical line carries the truth.
_MECHANICAL_TEMPLATES: dict[AspectType, str] = {
    AspectType.RELATIONSHIP: "{holder} is the {relation} of {target}",
    AspectType.AGENDA:       "{holder} is {method} in order to {goal}",
    AspectType.TABOO:        "{holder} will not discuss {subject} due to {origin}",
    AspectType.HISTORY:      "{holder} and {shared_with} share a {event_type} history",
    AspectType.IDENTITY:     "{holder} is concealing {fact}",
}


def primary_holder(secret: Secret) -> str | None:
    """Return the character id whose POV the secret is anchored to.

    OWNERs come first (they have the most to lose); if no OWNER is set,
    fall back to the first PARTICIPANT or WITNESS or SUSPECT in the
    listed order. ``None`` when the secret has no memberships at all.
    """
    role_priority = (
        SecretRole.OWNER,
        SecretRole.PARTICIPANT,
        SecretRole.WITNESS,
        SecretRole.SUSPECT,
    )
    for role in role_priority:
        for m in secret.memberships:
            if m.role == role:
                return m.character_id
    return None


def _readable_enum(value: Any) -> str:
    """Format an Enum value as a natural-language fragment.

    Replaces underscores with spaces and lowercases — keeps output
    in the mechanical sentence simple. Non-enum values pass through
    via ``str``.
    """
    raw = getattr(value, "value", str(value))
    return str(raw).replace("_", " ").strip()


def _resolve_name(character_id: str | None, cast: Mapping[str, str]) -> str:
    """Look up a name from the cast map. Falls back to the id when not
    listed (e.g. unbound placeholder ids)."""
    if not character_id:
        return "an unknown party"
    return cast.get(character_id, character_id)


def _aspect_to_mechanical(
    aspect: SecretAspect, holder_name: str, cast: Mapping[str, str]
) -> str:
    """Render one aspect as a single mechanical sentence."""
    template = _MECHANICAL_TEMPLATES[aspect.type]

    if isinstance(aspect, RelationshipAspect):
        return template.format(
            holder=holder_name,
            relation=_readable_enum(aspect.relation),
            target=_resolve_name(aspect.target, cast),
        )
    if isinstance(aspect, AgendaAspect):
        target_phrase = _resolve_name(aspect.target, cast)
        goal_phrase = _readable_enum(aspect.goal)
        # AgendaGoal values like "GAIN_LEVERAGE" benefit from the target
        # being inlined into the goal phrase — "gain leverage on rival".
        if aspect.target:
            goal_phrase = f"{goal_phrase} on {target_phrase}"
        return template.format(
            holder=holder_name,
            method=_readable_enum(aspect.method),
            goal=goal_phrase,
        )
    if isinstance(aspect, TabooAspect):
        return template.format(
            holder=holder_name,
            subject=_readable_enum(aspect.subject),
            origin=_readable_enum(aspect.origin),
        )
    if isinstance(aspect, HistoryAspect):
        names = [_resolve_name(cid, cast) for cid in aspect.shared_with]
        if len(names) == 0:
            shared = "someone"
        elif len(names) == 1:
            shared = names[0]
        else:
            shared = ", ".join(names[:-1]) + f" and {names[-1]}"
        return template.format(
            holder=holder_name,
            shared_with=shared,
            event_type=_readable_enum(aspect.event_type),
        )
    if isinstance(aspect, IdentityAspect):
        return template.format(
            holder=holder_name,
            fact=aspect.fact or "an identity fact",
        )
    raise TypeError(f"unknown aspect type: {type(aspect).__name__}")


def compose_mechanical_description(
    secret: Secret, cast: Mapping[str, str]
) -> str:
    """Render every aspect as mechanical sentences joined by ``. ``.

    Pure deterministic templating — no LLM call, no randomness. Output
    is the canonical truth that all later LLM stages must respect.
    Returns the empty string when the secret has no aspects.

    ``cast`` maps character ids (the strings stored on aspects) to
    display names. Unmapped ids fall through as the id itself, which
    makes placeholder ids visible during development.
    """
    holder_id = primary_holder(secret)
    holder_name = _resolve_name(holder_id, cast)
    parts = [
        _aspect_to_mechanical(a, holder_name, cast) for a in secret.aspects
    ]
    if not parts:
        return ""
    return ". ".join(parts) + "."


# ===========================================================================
# Step 2 — flavor_secret (LLM call 1)
# ===========================================================================


_FLAVOR_SYSTEM = (
    "You write spare, present-tense sentences. Do not contradict the "
    "mechanical fact. Do not invent characters or events. One short "
    "paragraph, two to three sentences."
)


def _flavor_user_prompt(mechanical: str, character_label: str) -> str:
    return (
        f"Mechanical fact (truth — do not contradict):\n{mechanical}\n\n"
        f"Subject: {character_label}\n\n"
        "Rewrite the mechanical fact as a brief, atmospheric description "
        "of the subject's situation. Keep every fact intact; add only "
        "tone, not new information."
    )


def flavor_secret(
    client: LLMClient,
    secret: Secret,
    *,
    cast: Mapping[str, str],
    character_label: str,
    fallback_to_mechanical: bool = True,
) -> str:
    """Run the flavor pass. Returns the mechanical sentence on any
    failure (LLM disabled, error, empty response).

    ``character_label`` is a free-text descriptor used in the prompt
    (e.g. ``"Player — striker, mid-twenties"``) so the LLM can ground
    voice. The function does *not* set ``secret.description`` — callers
    do that after consistency checks.
    """
    if secret.mechanical:
        mechanical = secret.mechanical
    else:
        mechanical = compose_mechanical_description(secret, cast)

    if not mechanical:
        return ""

    prompt = LLMPrompt(
        system=_FLAVOR_SYSTEM,
        user=_flavor_user_prompt(mechanical, character_label),
        max_tokens=150,
    )
    response = client.generate(prompt)
    if response is None or not response.strip():
        return mechanical if fallback_to_mechanical else ""
    return response.strip()


# ===========================================================================
# Step 3 — generate_aspect_phrases (LLM call 2, one per aspect)
# ===========================================================================


_ASPECT_PHRASES_SYSTEM = (
    "You write short narrator phrases for a stage drama. Output strictly "
    "JSON. Do not invent facts. Do not name the secret. Each phrase is "
    "one sentence."
)


_ASPECT_PHRASES_USER_TEMPLATE = (
    "Mechanical fact (truth — do not contradict): {mechanical}\n"
    "Description: {description}\n"
    "Aspect id: {aspect_id}\n\n"
    "Write four narrator phrases for this aspect at increasing "
    "revelation levels. Stay grounded in the mechanical fact.\n\n"
    "hidden:    vague sense only, 8-12 words, do not name the secret\n"
    "glimpsed:  something feels off, no specifics, 8-12 words\n"
    "suspected: shape is clear, details uncertain, 8-15 words\n"
    "known:     substantially understood, 8-15 words\n\n"
    "Respond as JSON with exactly these keys: "
    '{{"hidden": "...", "glimpsed": "...", "suspected": "...", '
    '"known": "..."}}.'
)


def _fallback_aspect_phrases(aspect_id: str, mechanical: str) -> AspectPhrases:
    """Deterministic phrase set used when the LLM is unavailable.

    Each band reads as progressively more of the mechanical sentence
    so reveal logic always has *something* to display. Authors can
    overwrite later by re-running ``initialise_secret`` with a working
    LLM client.
    """
    if not mechanical:
        return AspectPhrases(aspect_id=aspect_id)

    sentence = mechanical.rstrip(".")
    return AspectPhrases(
        aspect_id=aspect_id,
        hidden="Something is off, but nothing concrete shows.",
        glimpsed="A pattern starts to register without resolving.",
        suspected=f"It looks like {sentence}.",
        known=f"{sentence}.",
    )


def _parse_phrases_json(response: str, aspect_id: str) -> AspectPhrases | None:
    """Parse the JSON response into an AspectPhrases, or ``None`` when
    the response is malformed or missing required keys."""
    try:
        data = json.loads(response)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    required = ("hidden", "glimpsed", "suspected", "known")
    if not all(isinstance(data.get(k), str) and data[k].strip() for k in required):
        return None
    return AspectPhrases(
        aspect_id=aspect_id,
        hidden=data["hidden"].strip(),
        glimpsed=data["glimpsed"].strip(),
        suspected=data["suspected"].strip(),
        known=data["known"].strip(),
    )


def generate_aspect_phrases(
    client: LLMClient,
    aspect: SecretAspect,
    *,
    mechanical: str,
    description: str,
) -> AspectPhrases:
    """Produce the four-band phrase set for one aspect.

    Falls back to :func:`_fallback_aspect_phrases` on any LLM failure
    (disabled client, network error, malformed JSON, missing keys).
    The fallback is deterministic given the mechanical sentence.
    """
    prompt = LLMPrompt(
        system=_ASPECT_PHRASES_SYSTEM,
        user=_ASPECT_PHRASES_USER_TEMPLATE.format(
            mechanical=mechanical,
            description=description,
            aspect_id=aspect.id,
        ),
        max_tokens=300,
    )
    response = client.generate(prompt)
    if response is None:
        return _fallback_aspect_phrases(aspect.id, mechanical)
    parsed = _parse_phrases_json(response, aspect.id)
    if parsed is None:
        log.debug(
            "aspect phrase JSON parse failed for %s — using fallback",
            aspect.id,
        )
        return _fallback_aspect_phrases(aspect.id, mechanical)
    return parsed


# ===========================================================================
# Step 4 — reformulate_secret (LLM call 3, optional consistency pass)
# ===========================================================================


_REFORMULATE_SYSTEM = (
    "You polish a paragraph for tonal consistency without changing any "
    "fact. Do not introduce new entities."
)


def _reformulate_user_prompt(
    description: str,
    aspect_phrases: Mapping[str, AspectPhrases],
    mechanical: str,
) -> str:
    phrase_lines = []
    for phrases in aspect_phrases.values():
        phrase_lines.append(
            f"- known: {phrases.known}\n  suspected: {phrases.suspected}"
        )
    phrases_block = "\n".join(phrase_lines) if phrase_lines else "(none)"
    return (
        f"Mechanical fact: {mechanical}\n\n"
        f"Description:\n{description}\n\n"
        f"Aspect phrases:\n{phrases_block}\n\n"
        "Rewrite the description so the tone matches the aspect phrases. "
        "Keep every fact in the mechanical line. Two to three sentences."
    )


def needs_consistency_pass(secret: Secret) -> bool:
    """Heuristic: only run the optional reformulate pass when the
    secret has 3+ aspects (high chance of tonal drift across them).

    Authors can override by calling :func:`reformulate_secret`
    directly.
    """
    return len(secret.aspects) >= 3


def reformulate_secret(
    client: LLMClient,
    description: str,
    aspect_phrases: Mapping[str, AspectPhrases],
    mechanical: str,
) -> str:
    """Optional final pass that rewrites the description for tonal
    consistency with the generated aspect phrases. Returns the input
    description unchanged on any LLM failure.
    """
    prompt = LLMPrompt(
        system=_REFORMULATE_SYSTEM,
        user=_reformulate_user_prompt(description, aspect_phrases, mechanical),
        max_tokens=200,
    )
    response = client.generate(prompt)
    if response is None or not response.strip():
        return description
    return response.strip()


# ===========================================================================
# Orchestrator — initialise_secret
# ===========================================================================


def initialise_secret(
    secret: Secret,
    *,
    cast: Mapping[str, str],
    character_label: str,
    llm_client: LLMClient,
    run_consistency_pass: bool | None = None,
) -> Secret:
    """Run the full pipeline on ``secret`` in place. Returns the same
    object for convenience.

    Idempotent: re-running re-renders ``mechanical`` and the LLM
    outputs without raising. Callers preserving previous flavor
    should snapshot ``description`` / ``aspect_phrases`` before
    calling.

    ``run_consistency_pass`` defaults to :func:`needs_consistency_pass`
    (3+ aspects). Pass ``False`` to skip, ``True`` to force.
    """
    secret.mechanical = compose_mechanical_description(secret, cast)
    secret.description = flavor_secret(
        llm_client,
        secret,
        cast=cast,
        character_label=character_label,
    )
    secret.aspect_phrases = {
        a.id: generate_aspect_phrases(
            llm_client,
            a,
            mechanical=secret.mechanical,
            description=secret.description,
        )
        for a in secret.aspects
    }
    if run_consistency_pass is None:
        run_consistency_pass = needs_consistency_pass(secret)
    if run_consistency_pass:
        secret.description = reformulate_secret(
            llm_client,
            secret.description,
            secret.aspect_phrases,
            secret.mechanical,
        )
    return secret
