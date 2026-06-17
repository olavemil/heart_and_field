"""Figure asset model + selection (Phase 23 figure layer).

Face-less painterly figures composited over backgrounds. An asset is
keyed by ``(category, appearance, posture)``; selection maps a
character's persisted ``CharacterDescriptor`` to a coarse
``FigureAppearance`` and the event's ``EventTone`` to a ``FigurePosture``,
then picks the best-matching baked asset with graceful nearest-match
degradation so a missing exact combo still returns *something* in the
right category.

No image generation here — this is the data + selection layer the bake
driver (writes the manifest) and the composite layer (reads it) share.
See ``field_and_heart_figure_assets.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping

from .characters import CharacterRole
from .event_taxonomy import EventTone
from .sprite_pool import CharacterDescriptor


class FigureCategory(str, Enum):
    INTERLOCUTOR = "interlocutor"  # conversation partner facing the player
    AUTHORITY = "authority"        # manager / coach / official
    SERVICE = "service"            # waiter, cashier, vendor
    MEDICAL = "medical"            # nurse, doctor, physio
    OFFICE = "office"              # generic professional / media
    PLAYER = "player"             # the POV anchor (from-behind silhouette)
    MOTION = "motion"             # player-in-motion (match)
    ANONYMOUS = "anonymous"        # locker/shower/peripheral figures


class FigurePosture(str, Enum):
    # Conversation tones.
    WARM = "warm"
    NEUTRAL = "neutral"
    TENSE = "tense"
    # Authority set.
    COMFORTING = "comforting"
    SCEPTICAL = "sceptical"
    ANGRY = "angry"
    # Non-conversational.
    ACTION = "action"          # in motion
    PERIPHERAL = "peripheral"  # anonymous / joining-leaving


@dataclass(frozen=True)
class FigureAppearance:
    """Coarse appearance axes — deliberately low-resolution so abstract
    figures plausibly recur as different named characters."""

    gender: str = "masculine"       # masculine | feminine
    skin: str = "light"             # light | dark
    hair_color: str = "dark"        # dark | light | red
    hair_length: str = "short"      # short | long
    age: str = "adult"              # adult | older

    def to_dict(self) -> dict:
        return {
            "gender": self.gender, "skin": self.skin,
            "hair_color": self.hair_color, "hair_length": self.hair_length,
            "age": self.age,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "FigureAppearance":
        return cls(
            gender=str(d.get("gender", "masculine")),
            skin=str(d.get("skin", "light")),
            hair_color=str(d.get("hair_color", "dark")),
            hair_length=str(d.get("hair_length", "short")),
            age=str(d.get("age", "adult")),
        )


@dataclass(frozen=True)
class FigureAsset:
    category: FigureCategory
    appearance: FigureAppearance
    posture: FigurePosture
    path: str  # manifest-relative

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "appearance": self.appearance.to_dict(),
            "posture": self.posture.value,
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "FigureAsset":
        return cls(
            category=FigureCategory(d["category"]),
            appearance=FigureAppearance.from_dict(d["appearance"]),
            posture=FigurePosture(d["posture"]),
            path=str(d["path"]),
        )


@dataclass
class FigureManifest:
    """Registry of baked figure assets. Flat list; selection scores it."""

    assets_root: Path
    assets: list[FigureAsset] = field(default_factory=list)

    def add(self, asset: FigureAsset) -> None:
        self.assets.append(asset)

    def resolve(self, rel: str) -> Path:
        return self.assets_root / rel

    def to_dict(self) -> dict:
        return {"assets": [a.to_dict() for a in self.assets]}

    def save(self, path: Path | None = None) -> Path:
        out = path or (self.assets_root / "figures.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1))
        return out

    @classmethod
    def load(cls, assets_root: Path, path: Path | None = None) -> "FigureManifest":
        mf = cls(assets_root=Path(assets_root))
        src = path or (Path(assets_root) / "figures.json")
        if src.exists():
            data = json.loads(src.read_text())
            mf.assets = [FigureAsset.from_dict(a) for a in data.get("assets", [])]
        return mf


# --- Mapping helpers --------------------------------------------------------

_DARK_HAIR = ("brown", "black", "grey")


def appearance_from_descriptor(desc: CharacterDescriptor) -> FigureAppearance:
    """Coarsen a character's descriptor onto the figure appearance grid."""
    gender = desc.gender_presentation.value
    if gender not in ("masculine", "feminine"):
        gender = "masculine"  # androgynous → nearest bucket (abstract figure)

    skin = "dark" if desc.skin_tone.value == "dark" else "light"

    hair = desc.hair  # combined "length_colour" token, e.g. "short_black"
    if "blonde" in hair:
        hair_color = "light"
    elif "red" in hair:
        hair_color = "red"
    else:
        hair_color = "dark"
    hair_length = "short" if hair.startswith(("short", "buzz")) else "long"

    age = "older" if desc.age_bucket.value == "veteran" else "adult"
    return FigureAppearance(
        gender=gender, skin=skin, hair_color=hair_color,
        hair_length=hair_length, age=age,
    )


_AUTHORITY_TONE: dict[EventTone, FigurePosture] = {
    EventTone.HOSTILE: FigurePosture.ANGRY,
    EventTone.TENSE: FigurePosture.SCEPTICAL,
    EventTone.WARM: FigurePosture.COMFORTING,
    EventTone.ROMANTIC: FigurePosture.COMFORTING,
    EventTone.PLAYFUL: FigurePosture.COMFORTING,
    EventTone.TRIUMPHANT: FigurePosture.COMFORTING,
}
_INTERLOCUTOR_TONE: dict[EventTone, FigurePosture] = {
    EventTone.HOSTILE: FigurePosture.TENSE,
    EventTone.TENSE: FigurePosture.TENSE,
    EventTone.WARM: FigurePosture.WARM,
    EventTone.ROMANTIC: FigurePosture.WARM,
    EventTone.PLAYFUL: FigurePosture.WARM,
    EventTone.TRIUMPHANT: FigurePosture.WARM,
}


def posture_for(category: FigureCategory, tone: EventTone) -> FigurePosture:
    """Map an event tone onto a category-appropriate posture."""
    if category is FigureCategory.MOTION:
        return FigurePosture.ACTION
    if category is FigureCategory.ANONYMOUS:
        return FigurePosture.PERIPHERAL
    if category is FigureCategory.AUTHORITY:
        return _AUTHORITY_TONE.get(tone, FigurePosture.NEUTRAL)
    if category is FigureCategory.INTERLOCUTOR:
        return _INTERLOCUTOR_TONE.get(tone, FigurePosture.NEUTRAL)
    return FigurePosture.NEUTRAL


_PLAYING_ROLES = {
    CharacterRole.STRIKER, CharacterRole.MIDFIELDER,
    CharacterRole.DEFENDER, CharacterRole.GOALKEEPER,
}


def category_for_role(role: CharacterRole, *, in_match: bool = False) -> FigureCategory:
    """Pick the figure category for a cast member's role + context."""
    if in_match and role in _PLAYING_ROLES:
        return FigureCategory.MOTION
    if role in (CharacterRole.MANAGER, CharacterRole.ASSISTANT_COACH):
        return FigureCategory.AUTHORITY
    if role is CharacterRole.PHYSIO:
        return FigureCategory.MEDICAL
    if role is CharacterRole.MEDIA:
        return FigureCategory.OFFICE
    return FigureCategory.INTERLOCUTOR


# --- Selection --------------------------------------------------------------

# Appearance-axis match weights (gender/posture dominate identity read).
_W_GENDER = 8
_W_POSTURE = 6
_W_AGE = 2
_W_SKIN = 1
_W_HAIR_COLOR = 1
_W_HAIR_LENGTH = 1


def select_figure(
    manifest: FigureManifest,
    category: FigureCategory,
    appearance: FigureAppearance,
    posture: FigurePosture,
) -> FigureAsset | None:
    """Best-matching asset in *category*, or None if the category is empty.

    Scores every asset in the category; gender and posture dominate so a
    missing exact appearance degrades gracefully (a different hair colour
    before a wrong gender or emotional read). Deterministic on ties.
    """
    pool = [a for a in manifest.assets if a.category is category]
    if not pool:
        return None

    def score(a: FigureAsset) -> int:
        s = 0
        ap = a.appearance
        if ap.gender == appearance.gender:
            s += _W_GENDER
        if a.posture is posture:
            s += _W_POSTURE
        if ap.age == appearance.age:
            s += _W_AGE
        if ap.skin == appearance.skin:
            s += _W_SKIN
        if ap.hair_color == appearance.hair_color:
            s += _W_HAIR_COLOR
        if ap.hair_length == appearance.hair_length:
            s += _W_HAIR_LENGTH
        return s

    # max() keeps the first asset on ties → deterministic given a stable
    # manifest order.
    return max(pool, key=score)


def select_for_character(
    manifest: FigureManifest,
    descriptor: CharacterDescriptor,
    role: CharacterRole,
    tone: EventTone,
    *,
    in_match: bool = False,
) -> FigureAsset | None:
    """Convenience: descriptor + role + tone → asset."""
    category = category_for_role(role, in_match=in_match)
    appearance = appearance_from_descriptor(descriptor)
    posture = posture_for(category, tone)
    return select_figure(manifest, category, appearance, posture)
