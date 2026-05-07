"""Secret system (addendum §3) — Phase 13 (structural) only.

A secret is a typed bundle of *aspects* (relationship, agenda, taboo,
history, identity), bound to one or more characters via *memberships*
(owner / participant / witness / suspect). Aspects expose progressively
through play via four ``ExposureBand`` levels — the LLM that produces
banded narration (`hidden`, `glimpsed`, `suspected`, `known` strings)
lands in Phase 14; this module builds the data structures and the
observer-perspective reveal logic.

Reveal symmetry with quirks (Phase 12):
- Both subsystems are observer-perspective: the same secret/quirk reads
  differently to different watchers.
- Both accept ``witnessed_event_tags`` and a familiarity float as the
  same observer-side inputs (see :func:`aspect_band_for_observer` and
  :func:`engine.quirks.visible_to_observer`).
- Quirks return a binary ``visible / not visible``; secrets return one
  of four ``ExposureBand`` levels because the addendum specifies four
  bands of authored narration. The signature shape is intentionally
  parallel so call sites read the same way.

LLM and placeholder pipelines (Phases 14–15) hang off this module and
populate ``Secret.mechanical``, ``Secret.description``, and
``Secret.aspect_phrases``. This phase leaves those empty by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Union


# ===========================================================================
# Top-level enums
# ===========================================================================


class SecretCategory(str, Enum):
    AGENDA = "agenda"
    TABOO = "taboo"
    CONNECTION = "connection"
    HISTORY = "history"
    IDENTITY = "identity"


class SecretRole(str, Enum):
    """Membership role on a single secret (addendum §3.1)."""

    OWNER = "owner"             # holds the secret, most to lose
    PARTICIPANT = "participant" # involved, may not know the full shape
    WITNESS = "witness"         # knows, not involved — most dangerous
    SUSPECT = "suspect"         # doesn't know, but others think they might


class SecretRelationType(str, Enum):
    """How two secrets relate across characters (addendum §3.4)."""

    SHARED = "shared"        # both hold the same secret
    OPPOSING = "opposing"    # their secrets conflict
    DEPENDENT = "dependent"  # this secret only matters because of theirs
    AWARE_OF = "aware_of"    # this character knows the other's secret


class ExposureBand(str, Enum):
    """Four bands of authored narration (addendum §3.5).

    Names match the field names on :class:`AspectPhrases` so
    ``getattr(phrases, band.value)`` round-trips cleanly.
    """

    HIDDEN = "hidden"        # 0.0–0.2  almost nothing visible
    GLIMPSED = "glimpsed"    # 0.2–0.5  something is off
    SUSPECTED = "suspected"  # 0.5–0.8  shape is clear, details uncertain
    KNOWN = "known"          # 0.8–1.0  substantially understood


_BAND_ORDER: tuple[ExposureBand, ...] = (
    ExposureBand.HIDDEN,
    ExposureBand.GLIMPSED,
    ExposureBand.SUSPECTED,
    ExposureBand.KNOWN,
)


def exposure_band(exposure: float) -> ExposureBand:
    """Project a continuous exposure value to its band.

    Cutpoints follow the addendum: 0.0–0.2 hidden, 0.2–0.5 glimpsed,
    0.5–0.8 suspected, 0.8–1.0 known. Out-of-range values clamp to the
    nearest band.
    """
    if exposure < 0.2:
        return ExposureBand.HIDDEN
    if exposure < 0.5:
        return ExposureBand.GLIMPSED
    if exposure < 0.8:
        return ExposureBand.SUSPECTED
    return ExposureBand.KNOWN


def _bump_band(band: ExposureBand, *, cap: ExposureBand | None = None) -> ExposureBand:
    """Move one band up. ``cap`` limits how far the bump can reach."""
    idx = _BAND_ORDER.index(band)
    if idx >= len(_BAND_ORDER) - 1:
        return band
    nxt = _BAND_ORDER[idx + 1]
    if cap is not None and _BAND_ORDER.index(nxt) > _BAND_ORDER.index(cap):
        return cap
    return nxt


# ===========================================================================
# Aspect taxonomy (addendum §3.3)
# ===========================================================================


class AspectType(str, Enum):
    RELATIONSHIP = "relationship"
    AGENDA = "agenda"
    TABOO = "taboo"
    HISTORY = "history"
    IDENTITY = "identity"


# --- RELATIONSHIP ---------------------------------------------------------


class RelationType(str, Enum):
    PARENT = "parent"
    CHILD = "child"
    SIBLING = "sibling"
    FORMER_LOVER = "former_lover"
    CURRENT_LOVER = "current_lover"
    MENTOR = "mentor"
    PROTEGE = "protege"
    CREDITOR = "creditor"
    DEBTOR = "debtor"
    FORMER_TEAMMATE = "former_teammate"
    EMPLOYER = "employer"
    RIVAL = "rival"


# --- AGENDA --------------------------------------------------------------


class AgendaGoal(str, Enum):
    PROTECT_CHARACTER = "protect_character"
    SECURE_TRANSFER = "secure_transfer"
    EXPOSE_CHARACTER = "expose_character"
    PRESERVE_POSITION = "preserve_position"
    GAIN_LEVERAGE = "gain_leverage"
    SEEK_RECONCILIATION = "seek_reconciliation"
    SABOTAGE_CHARACTER = "sabotage_character"
    EXTRACT_INFORMATION = "extract_information"


class AgendaMethod(str, Enum):
    INGRATIATING = "ingratiating"
    OBSERVING = "observing"
    MANIPULATING = "manipulating"
    CONFIDING = "confiding"
    ISOLATING = "isolating"
    PERFORMING = "performing"


# --- TABOO ---------------------------------------------------------------


class TabooSubject(str, Enum):
    FAMILY_CONNECTION = "family_connection"
    PAST_INCIDENT = "past_incident"
    FORMER_CLUB = "former_club"
    HEALTH_CONDITION = "health_condition"
    FINANCIAL_SITUATION = "financial_situation"
    IDENTITY_FACT = "identity_fact"
    RELATIONSHIP = "relationship"


class TabooOrigin(str, Enum):
    CONTRACTUAL = "contractual"
    SHAME = "shame"
    PROTECTION = "protection"
    TRAUMA = "trauma"
    LEGAL = "legal"
    PROFESSIONAL = "professional"


# --- HISTORY -------------------------------------------------------------


class HistoryEventType(str, Enum):
    PREVIOUS_CLUB = "previous_club"
    ROMANTIC = "romantic"
    INCIDENT = "incident"
    SHARED_LOSS = "shared_loss"
    BETRAYAL = "betrayal"
    COLLABORATION = "collaboration"
    RIVALRY = "rivalry"


# ===========================================================================
# Aspect dataclasses
# ===========================================================================
#
# Each concrete aspect is a separate dataclass. Polymorphic (de)serialise
# dispatches on the ``type`` field via :func:`aspect_from_dict`. This
# flat structure beats inheritance + default field overriding when it
# comes to dataclass ergonomics.


@dataclass
class RelationshipAspect:
    """Two characters connected by a hidden relationship."""

    id: str
    relation: RelationType
    target: str | None = None  # character id or placeholder id
    mutual: bool = False  # does the target know?
    type: AspectType = AspectType.RELATIONSHIP

    def to_dict(self) -> dict:
        return {
            "type": AspectType.RELATIONSHIP.value,
            "id": self.id,
            "relation": self.relation.value,
            "target": self.target,
            "mutual": self.mutual,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "RelationshipAspect":
        return cls(
            id=str(d["id"]),
            relation=RelationType(d["relation"]),
            target=d.get("target"),
            mutual=bool(d.get("mutual", False)),
        )


@dataclass
class AgendaAspect:
    """A pursued goal hidden behind a method (e.g. ingratiating to gain leverage)."""

    id: str
    goal: AgendaGoal
    method: AgendaMethod
    target: str | None = None
    type: AspectType = AspectType.AGENDA

    def to_dict(self) -> dict:
        return {
            "type": AspectType.AGENDA.value,
            "id": self.id,
            "goal": self.goal.value,
            "method": self.method.value,
            "target": self.target,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "AgendaAspect":
        return cls(
            id=str(d["id"]),
            goal=AgendaGoal(d["goal"]),
            method=AgendaMethod(d["method"]),
            target=d.get("target"),
        )


@dataclass
class TabooAspect:
    """A subject the holder won't discuss, with an origin shaping how
    it surfaces (shame, contractual silence, trauma, …)."""

    id: str
    subject: TabooSubject
    origin: TabooOrigin
    trigger_tags: list[str] = field(default_factory=list)
    type: AspectType = AspectType.TABOO

    def to_dict(self) -> dict:
        return {
            "type": AspectType.TABOO.value,
            "id": self.id,
            "subject": self.subject.value,
            "origin": self.origin.value,
            "trigger_tags": list(self.trigger_tags),
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "TabooAspect":
        return cls(
            id=str(d["id"]),
            subject=TabooSubject(d["subject"]),
            origin=TabooOrigin(d["origin"]),
            trigger_tags=list(d.get("trigger_tags", [])),
        )


@dataclass
class HistoryAspect:
    """A shared past event between characters that's no longer talked about."""

    id: str
    event_type: HistoryEventType
    shared_with: list[str] = field(default_factory=list)  # character ids
    known_to: list[str] = field(default_factory=list)     # who already knows
    type: AspectType = AspectType.HISTORY

    def to_dict(self) -> dict:
        return {
            "type": AspectType.HISTORY.value,
            "id": self.id,
            "event_type": self.event_type.value,
            "shared_with": list(self.shared_with),
            "known_to": list(self.known_to),
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "HistoryAspect":
        return cls(
            id=str(d["id"]),
            event_type=HistoryEventType(d["event_type"]),
            shared_with=list(d.get("shared_with", [])),
            known_to=list(d.get("known_to", [])),
        )


@dataclass
class IdentityAspect:
    """A concealed identity fact (e.g. real name, citizenship, age).

    The addendum mentions IDENTITY but doesn't expand the sub-enums;
    ``fact`` is a free-text label until later phases pin it down.
    """

    id: str
    fact: str
    type: AspectType = AspectType.IDENTITY

    def to_dict(self) -> dict:
        return {
            "type": AspectType.IDENTITY.value,
            "id": self.id,
            "fact": self.fact,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "IdentityAspect":
        return cls(id=str(d["id"]), fact=str(d.get("fact", "")))


SecretAspect = Union[
    RelationshipAspect,
    AgendaAspect,
    TabooAspect,
    HistoryAspect,
    IdentityAspect,
]


_ASPECT_FROM_DICT = {
    AspectType.RELATIONSHIP: RelationshipAspect.from_dict,
    AspectType.AGENDA: AgendaAspect.from_dict,
    AspectType.TABOO: TabooAspect.from_dict,
    AspectType.HISTORY: HistoryAspect.from_dict,
    AspectType.IDENTITY: IdentityAspect.from_dict,
}


def aspect_from_dict(d: Mapping) -> SecretAspect:
    """Polymorphic deserialise — picks the right aspect class via
    the ``type`` discriminator stored on the dict."""
    t = AspectType(d["type"])
    return _ASPECT_FROM_DICT[t](d)


def aspect_to_dict(a: SecretAspect) -> dict:
    return a.to_dict()


# ===========================================================================
# Membership and cross-secret relations
# ===========================================================================


@dataclass
class SecretMembership:
    """A character's link to a secret (addendum §3.1)."""

    character_id: str
    role: SecretRole
    exposure: float = 0.0  # how much of the secret this member knows [0..1]
    knows_other_members: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "character_id": self.character_id,
            "role": self.role.value,
            "exposure": self.exposure,
            "knows_other_members": list(self.knows_other_members),
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "SecretMembership":
        return cls(
            character_id=str(d["character_id"]),
            role=SecretRole(d["role"]),
            exposure=float(d.get("exposure", 0.0)),
            knows_other_members=list(d.get("knows_other_members", [])),
        )


@dataclass
class SecretRelation:
    """Cross-character / cross-secret link (addendum §3.4)."""

    other_character_id: str
    other_secret_id: str
    relation_type: SecretRelationType

    def to_dict(self) -> dict:
        return {
            "other_character_id": self.other_character_id,
            "other_secret_id": self.other_secret_id,
            "relation_type": self.relation_type.value,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "SecretRelation":
        return cls(
            other_character_id=str(d["other_character_id"]),
            other_secret_id=str(d["other_secret_id"]),
            relation_type=SecretRelationType(d["relation_type"]),
        )


# ===========================================================================
# Banded narration (addendum §3.5)
# ===========================================================================


@dataclass
class AspectPhrases:
    """Four authored phrases for an aspect, one per exposure band.

    Generated by the LLM pipeline (Phase 14) at character init and
    cached on :class:`Secret`. Empty strings are valid before
    initialisation runs.
    """

    aspect_id: str
    hidden: str = ""
    glimpsed: str = ""
    suspected: str = ""
    known: str = ""

    def by_band(self, band: ExposureBand) -> str:
        """Return the phrase for a band — keys match :class:`ExposureBand`
        values so this is just attribute lookup."""
        return getattr(self, band.value)

    def to_dict(self) -> dict:
        return {
            "aspect_id": self.aspect_id,
            "hidden": self.hidden,
            "glimpsed": self.glimpsed,
            "suspected": self.suspected,
            "known": self.known,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "AspectPhrases":
        return cls(
            aspect_id=str(d["aspect_id"]),
            hidden=str(d.get("hidden", "")),
            glimpsed=str(d.get("glimpsed", "")),
            suspected=str(d.get("suspected", "")),
            known=str(d.get("known", "")),
        )


# ===========================================================================
# Secret + MetaSecret
# ===========================================================================


@dataclass
class MetaSecret:
    """A secret about another character's secret (one level deep).

    Spawned by ``SecretRelationType.AWARE_OF`` — Character A's secret
    is that they know Character B's secret. Hard-capped at one layer:
    a meta-secret cannot itself spawn another. Validation lives in
    :meth:`Secret.__post_init__`.
    """

    id: str
    base_secret_id: str
    aspects: list[SecretAspect] = field(default_factory=list)
    memberships: list[SecretMembership] = field(default_factory=list)
    is_meta: bool = True
    mechanical: str = ""
    description: str = ""
    aspect_phrases: dict[str, AspectPhrases] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "base_secret_id": self.base_secret_id,
            "aspects": [aspect_to_dict(a) for a in self.aspects],
            "memberships": [m.to_dict() for m in self.memberships],
            "is_meta": self.is_meta,
            "mechanical": self.mechanical,
            "description": self.description,
            "aspect_phrases": {
                k: v.to_dict() for k, v in self.aspect_phrases.items()
            },
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "MetaSecret":
        return cls(
            id=str(d["id"]),
            base_secret_id=str(d["base_secret_id"]),
            aspects=[aspect_from_dict(a) for a in d.get("aspects", [])],
            memberships=[
                SecretMembership.from_dict(m) for m in d.get("memberships", [])
            ],
            is_meta=bool(d.get("is_meta", True)),
            mechanical=str(d.get("mechanical", "")),
            description=str(d.get("description", "")),
            aspect_phrases={
                k: AspectPhrases.from_dict(v)
                for k, v in d.get("aspect_phrases", {}).items()
            },
        )


@dataclass
class Secret:
    """A bundle of typed aspects bound to characters and exposed
    progressively through play (addendum §3.2).

    Mechanical / description / aspect_phrases stay empty until the
    Phase 14 LLM pipeline initialises them. Reveal mechanics
    (:func:`aspect_band_for_observer`) are usable from creation.
    """

    id: str
    category: SecretCategory
    aspects: list[SecretAspect] = field(default_factory=list)
    memberships: list[SecretMembership] = field(default_factory=list)
    related_secrets: list[SecretRelation] = field(default_factory=list)

    unlocks_arcs: list[str] = field(default_factory=list)
    blocks_arcs: list[str] = field(default_factory=list)
    unlocks_events: list[str] = field(default_factory=list)

    exposure_level: float = 0.0  # global non-member-perceived exposure [0..1]
    reveal_triggers: list[str] = field(default_factory=list)  # event tags
    reveal_threshold: float = 0.8  # global exposure at which non-members see it

    # Generated by ``initialise_secret`` (Phase 14):
    mechanical: str = ""
    description: str = ""
    aspect_phrases: dict[str, AspectPhrases] = field(default_factory=dict)

    # AWARE_OF spawns a single meta-secret; further nesting is invalid.
    meta_secret: MetaSecret | None = None

    def __post_init__(self):
        if self.meta_secret is not None and not self.meta_secret.is_meta:
            raise ValueError(
                f"meta_secret on {self.id!r} must have is_meta=True"
            )

    # --- Lookup ------------------------------------------------------

    def membership_for(self, character_id: str) -> SecretMembership | None:
        for m in self.memberships:
            if m.character_id == character_id:
                return m
        return None

    def aspect_for(self, aspect_id: str) -> SecretAspect | None:
        for a in self.aspects:
            if a.id == aspect_id:
                return a
        return None

    # --- Persistence -------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category.value,
            "aspects": [aspect_to_dict(a) for a in self.aspects],
            "memberships": [m.to_dict() for m in self.memberships],
            "related_secrets": [r.to_dict() for r in self.related_secrets],
            "unlocks_arcs": list(self.unlocks_arcs),
            "blocks_arcs": list(self.blocks_arcs),
            "unlocks_events": list(self.unlocks_events),
            "exposure_level": self.exposure_level,
            "reveal_triggers": list(self.reveal_triggers),
            "reveal_threshold": self.reveal_threshold,
            "mechanical": self.mechanical,
            "description": self.description,
            "aspect_phrases": {
                k: v.to_dict() for k, v in self.aspect_phrases.items()
            },
            "meta_secret": (
                self.meta_secret.to_dict() if self.meta_secret is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "Secret":
        meta = d.get("meta_secret")
        return cls(
            id=str(d["id"]),
            category=SecretCategory(d["category"]),
            aspects=[aspect_from_dict(a) for a in d.get("aspects", [])],
            memberships=[
                SecretMembership.from_dict(m) for m in d.get("memberships", [])
            ],
            related_secrets=[
                SecretRelation.from_dict(r) for r in d.get("related_secrets", [])
            ],
            unlocks_arcs=list(d.get("unlocks_arcs", [])),
            blocks_arcs=list(d.get("blocks_arcs", [])),
            unlocks_events=list(d.get("unlocks_events", [])),
            exposure_level=float(d.get("exposure_level", 0.0)),
            reveal_triggers=list(d.get("reveal_triggers", [])),
            reveal_threshold=float(d.get("reveal_threshold", 0.8)),
            mechanical=str(d.get("mechanical", "")),
            description=str(d.get("description", "")),
            aspect_phrases={
                k: AspectPhrases.from_dict(v)
                for k, v in d.get("aspect_phrases", {}).items()
            },
            meta_secret=MetaSecret.from_dict(meta) if meta is not None else None,
        )


# ===========================================================================
# Reveal — observer-perspective (addendum §3.8)
# ===========================================================================


def aspect_band_for_observer(
    secret: Secret,
    aspect_id: str,
    *,
    observer_id: str,
    observer_familiarity: float = 0.0,
    witnessed_event_tags: Iterable[str] = (),
) -> ExposureBand:
    """Return the exposure band the observer reads this aspect at.

    Symmetry with :func:`engine.quirks.visible_to_observer`: same
    observer-side inputs (``witnessed_event_tags`` + a familiarity
    float). Logic differs because secrets carry membership and four
    bands; quirks carry three discrete visibility states.

    Members (any :class:`SecretRole`) see at their membership's
    ``exposure`` band — they're inside the secret, so witnessed events
    don't change what they already know.

    Non-members start at the band of ``secret.exposure_level``. A
    matching event tag in ``secret.reveal_triggers`` *or* familiarity
    above ``secret.reveal_threshold`` bumps the band up by one,
    capped at ``SUSPECTED`` — non-members never reach ``KNOWN`` from
    inference alone.
    """
    membership = secret.membership_for(observer_id)
    if membership is not None:
        return exposure_band(membership.exposure)

    base = exposure_band(secret.exposure_level)
    triggered = bool(set(witnessed_event_tags) & set(secret.reveal_triggers))
    familiar = observer_familiarity >= secret.reveal_threshold
    if triggered or familiar:
        return _bump_band(base, cap=ExposureBand.SUSPECTED)
    return base


def aspect_phrase_for_observer(
    secret: Secret,
    aspect_id: str,
    *,
    observer_id: str,
    observer_familiarity: float = 0.0,
    witnessed_event_tags: Iterable[str] = (),
) -> str | None:
    """Compose :func:`aspect_band_for_observer` with the secret's
    authored phrase pool.

    Returns ``None`` when the band is ``HIDDEN`` (nothing visible),
    when the aspect isn't on this secret, or when the LLM pipeline
    hasn't filled in the phrases yet (Phase 14). When the band is
    above hidden, returns the matching string from
    :class:`AspectPhrases`.
    """
    if secret.aspect_for(aspect_id) is None:
        return None
    band = aspect_band_for_observer(
        secret,
        aspect_id,
        observer_id=observer_id,
        observer_familiarity=observer_familiarity,
        witnessed_event_tags=witnessed_event_tags,
    )
    if band == ExposureBand.HIDDEN:
        return None
    phrases = secret.aspect_phrases.get(aspect_id)
    if phrases is None:
        return None
    return phrases.by_band(band)


def secret_visible_to(
    secret: Secret,
    observer_id: str,
    aspect_id: str,
    *,
    observer_familiarity: float = 0.0,
    witnessed_event_tags: Iterable[str] = (),
) -> tuple[bool, str | None]:
    """Convenience wrapper: ``(visible, phrase_or_None)``.

    Mirrors the addendum §3.8 signature. ``visible`` is True for any
    band above HIDDEN; ``phrase`` is the authored line for that band
    (or ``None`` when the LLM pipeline hasn't filled it).
    """
    band = aspect_band_for_observer(
        secret,
        aspect_id,
        observer_id=observer_id,
        observer_familiarity=observer_familiarity,
        witnessed_event_tags=witnessed_event_tags,
    )
    if band == ExposureBand.HIDDEN:
        return False, None
    phrases = secret.aspect_phrases.get(aspect_id)
    return True, (phrases.by_band(band) if phrases is not None else None)
