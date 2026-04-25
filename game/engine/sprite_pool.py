"""Sprite pool: character-creator descriptor, sprite manifest, reuse lookup.

The **descriptor** is the character-creator's lever set. Its ``bucket_key``
is the manifest's primary key — if two descriptors bucket to the same key,
their sprite can be reused.

The **manifest** is a JSON file persisted alongside the sprite images in
``game/assets/characters/``. It tracks every generated sprite set, what
descriptor it came from, and whether a character has claimed it.

The flow:
    1. Cast needs a character matching a descriptor.
    2. ``find_unclaimed(descriptor)`` returns a free sprite set, or ``None``.
    3. If ``None``, the generation pipeline produces one and ``add_entry``
       registers it.
    4. ``claim(entry_id, character_id)`` locks the sprite to that character;
       ``release`` frees it when the character leaves play.

Authored sprites (Tier A marquee characters) can be pre-registered with
``reserved_for`` set so they're never offered to reuse lookups.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping


# ---------------------------------------------------------------------------
# Descriptor — character-creator axes = manifest key
# ---------------------------------------------------------------------------


class GenderPresentation(str, Enum):
    MASCULINE = "masculine"
    FEMININE = "feminine"
    ANDROGYNOUS = "androgynous"


class AgeBucket(str, Enum):
    YOUNG = "young"      # late teens / early twenties
    ADULT = "adult"      # mid-twenties / early thirties
    VETERAN = "veteran"  # mid-thirties and up


class SkinTone(str, Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    DARK = "dark"


class Build(str, Enum):
    LEAN = "lean"
    ATHLETIC = "athletic"
    STOCKY = "stocky"


@dataclass(frozen=True)
class CharacterDescriptor:
    """The levers the character creator exposes — and nothing more.

    Anything that changes requires regeneration; anything that doesn't
    (expression, mood tint, kit colour) belongs in layers or overlays
    instead, not in the descriptor.

    ``hair`` is a single combined style+colour token (e.g. ``"short_black"``,
    ``"long_brown"``) because the two are usually authored as one sprite.
    """

    gender_presentation: GenderPresentation = GenderPresentation.MASCULINE
    age_bucket: AgeBucket = AgeBucket.ADULT
    skin_tone: SkinTone = SkinTone.MEDIUM
    build: Build = Build.ATHLETIC
    hair: str = "short_brown"
    facial_hair: bool = False
    glasses: bool = False
    # Free-text anchoring for specific appearance details (eye colour,
    # freckles, scars, hair texture, brow shape, etc.). Included in
    # every generation prompt so variants stay consistent. Leave empty
    # for poolable Tier D sprites — the model picks details at random
    # and img2img anchoring handles the rest.
    appearance_details: str = ""

    def bucket_key(self) -> str:
        """Canonical key for reuse lookup.

        Two descriptors that bucket to the same key can share a sprite.
        Accessories (facial hair, glasses) participate so the sprite
        actually matches the silhouette.
        """
        parts = [
            self.gender_presentation.value,
            self.age_bucket.value,
            self.skin_tone.value,
            self.build.value,
            self.hair,
            "fh" if self.facial_hair else "nf",
            "gl" if self.glasses else "ng",
        ]
        # appearance_details participates via hash so that two descriptors
        # with different specifics don't collide, but empty details don't
        # change the key for poolable sprites.
        if self.appearance_details:
            detail_hash = hashlib.sha256(
                self.appearance_details.encode("utf-8")
            ).hexdigest()[:6]
            parts.append(f"d{detail_hash}")
        return "_".join(parts)

    def short_hash(self) -> str:
        """Short hex hash of the bucket key — useful for filesystem paths."""
        h = hashlib.sha256(self.bucket_key().encode("utf-8")).hexdigest()
        return h[:8]

    def to_prompt_fragment(self) -> str:
        """Natural-language description for the generation prompt.

        Kept minimal — the generator prepends role/context. Adjectives
        here are descriptor-faithful, not artful.
        """
        age_map = {
            AgeBucket.YOUNG: "person in their early twenties",
            AgeBucket.ADULT: "person in their late twenties",
            AgeBucket.VETERAN: "person in their late thirties",
        }
        skin_map = {
            SkinTone.LIGHT: "light skin",
            SkinTone.MEDIUM: "medium skin tone",
            SkinTone.DARK: "dark skin",
        }
        build_map = {
            Build.LEAN: "lean build",
            Build.ATHLETIC: "athletic build",
            Build.STOCKY: "stocky muscular build",
        }
        hair_readable = self.hair.replace("_", " ") + " hair"

        fragments = [
            age_map[self.age_bucket],
            skin_map[self.skin_tone],
            build_map[self.build],
            hair_readable,
            f"{self.gender_presentation.value} presenting",
        ]
        if self.facial_hair:
            fragments.append("trimmed facial hair")
        if self.glasses:
            fragments.append("wearing glasses")
        if self.appearance_details:
            fragments.append(self.appearance_details)
        return ", ".join(fragments)

    def to_dict(self) -> dict:
        return {
            "gender_presentation": self.gender_presentation.value,
            "age_bucket": self.age_bucket.value,
            "skin_tone": self.skin_tone.value,
            "build": self.build.value,
            "hair": self.hair,
            "facial_hair": self.facial_hair,
            "glasses": self.glasses,
            "appearance_details": self.appearance_details,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "CharacterDescriptor":
        return cls(
            gender_presentation=GenderPresentation(
                d.get("gender_presentation", GenderPresentation.MASCULINE.value)
            ),
            age_bucket=AgeBucket(d.get("age_bucket", AgeBucket.ADULT.value)),
            skin_tone=SkinTone(d.get("skin_tone", SkinTone.MEDIUM.value)),
            build=Build(d.get("build", Build.ATHLETIC.value)),
            hair=str(d.get("hair", "short_brown")),
            facial_hair=bool(d.get("facial_hair", False)),
            glasses=bool(d.get("glasses", False)),
            appearance_details=str(d.get("appearance_details", "")),
        )


# ---------------------------------------------------------------------------
# SpriteEntry — one row in the manifest
# ---------------------------------------------------------------------------


@dataclass
class SpriteEntry:
    """A generated sprite set linked to a descriptor and optionally claimed.

    Paths are stored relative to the manifest's assets root so the
    repository remains portable.
    """

    entry_id: str  # e.g. "masculine_adult_medium_athletic_short_brown_nf_ng_0"
    descriptor: CharacterDescriptor
    neutral_path: str  # relative to assets_root
    variants: dict[str, str] = field(default_factory=dict)  # expression → path
    claimed_by: str | None = None  # character_id when in use
    reserved_for: str | None = None  # if set, only this character may claim

    def is_available_for(self, character_id: str) -> bool:
        if self.claimed_by is not None:
            return self.claimed_by == character_id
        if self.reserved_for is not None:
            return self.reserved_for == character_id
        return True

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "descriptor": self.descriptor.to_dict(),
            "neutral_path": self.neutral_path,
            "variants": dict(self.variants),
            "claimed_by": self.claimed_by,
            "reserved_for": self.reserved_for,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "SpriteEntry":
        return cls(
            entry_id=str(d["entry_id"]),
            descriptor=CharacterDescriptor.from_dict(d["descriptor"]),
            neutral_path=str(d["neutral_path"]),
            variants=dict(d.get("variants", {})),
            claimed_by=d.get("claimed_by"),
            reserved_for=d.get("reserved_for"),
        )


# ---------------------------------------------------------------------------
# SpriteManifest — persisted pool
# ---------------------------------------------------------------------------


DEFAULT_MANIFEST_NAME = "manifest.json"


@dataclass
class SpriteManifest:
    """JSON-backed store of generated sprite sets.

    ``assets_root`` is the directory under which every sprite path is
    resolved. ``manifest_path`` defaults to ``assets_root/manifest.json``.
    """

    assets_root: Path
    entries: list[SpriteEntry] = field(default_factory=list)
    manifest_path: Path | None = None

    # --- Paths ---------------------------------------------------------

    def _path(self) -> Path:
        return self.manifest_path or (self.assets_root / DEFAULT_MANIFEST_NAME)

    def resolve(self, relative_path: str) -> Path:
        """Turn a manifest-stored relative path into an absolute file path."""
        return self.assets_root / relative_path

    # --- Persistence ---------------------------------------------------

    def save(self) -> Path:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "entries": [e.to_dict() for e in self.entries],
        }
        path.write_text(json.dumps(payload, indent=2))
        return path

    @classmethod
    def load(
        cls, assets_root: Path, manifest_path: Path | None = None
    ) -> "SpriteManifest":
        mf = cls(assets_root=Path(assets_root), manifest_path=manifest_path)
        path = mf._path()
        if path.exists():
            payload = json.loads(path.read_text())
            mf.entries = [
                SpriteEntry.from_dict(e) for e in payload.get("entries", [])
            ]
        return mf

    # --- Lookup --------------------------------------------------------

    def find_unclaimed(
        self,
        descriptor: CharacterDescriptor,
        character_id: str | None = None,
    ) -> SpriteEntry | None:
        """Return an entry matching ``descriptor`` that's free for reuse.

        ``character_id`` lets reserved-for sprites match their owner.
        """
        key = descriptor.bucket_key()
        for entry in self.entries:
            if entry.descriptor.bucket_key() != key:
                continue
            if character_id is not None and entry.is_available_for(character_id):
                return entry
            if character_id is None and entry.claimed_by is None and entry.reserved_for is None:
                return entry
        return None

    def get(self, entry_id: str) -> SpriteEntry | None:
        for entry in self.entries:
            if entry.entry_id == entry_id:
                return entry
        return None

    def entries_for_bucket(self, descriptor: CharacterDescriptor) -> list[SpriteEntry]:
        key = descriptor.bucket_key()
        return [e for e in self.entries if e.descriptor.bucket_key() == key]

    # --- Mutations -----------------------------------------------------

    def next_entry_id(self, descriptor: CharacterDescriptor) -> str:
        """Generate a stable, human-readable entry id for this bucket."""
        existing = self.entries_for_bucket(descriptor)
        return f"{descriptor.bucket_key()}_{len(existing)}"

    def add_entry(self, entry: SpriteEntry) -> SpriteEntry:
        if self.get(entry.entry_id) is not None:
            raise ValueError(f"duplicate entry_id: {entry.entry_id!r}")
        self.entries.append(entry)
        return entry

    def claim(self, entry_id: str, character_id: str) -> SpriteEntry:
        entry = self.get(entry_id)
        if entry is None:
            raise KeyError(f"unknown entry_id: {entry_id!r}")
        if not entry.is_available_for(character_id):
            raise RuntimeError(
                f"entry {entry_id!r} already claimed by {entry.claimed_by!r}"
            )
        entry.claimed_by = character_id
        return entry

    def release(self, entry_id: str) -> SpriteEntry:
        entry = self.get(entry_id)
        if entry is None:
            raise KeyError(f"unknown entry_id: {entry_id!r}")
        entry.claimed_by = None
        return entry

    def unclaimed_count(self, descriptor: CharacterDescriptor) -> int:
        return sum(
            1
            for e in self.entries_for_bucket(descriptor)
            if e.claimed_by is None and e.reserved_for is None
        )
