"""Stock face pool — pre-generated reference faces for img2img generation.

The pool contains a small set of high-quality face portraits generated
offline via ``scripts/generate_stock_faces.py``. At runtime, the visual
pipeline picks a stock face matching the character's gender presentation
(deterministic from the character seed) and uses it as an img2img anchor.
This produces faces that always look structurally correct while still
varying by character.

The pool is optional: when no stock faces are available the system falls
back to the placeholder face generator.
"""

from __future__ import annotations

import json
import random as _random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

DEFAULT_STOCK_DIR = "stock_faces"
MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class StockFace:
    """One pre-generated reference face."""

    filename: str
    gender_presentation: str  # "masculine", "feminine", "androgynous"
    age_bucket: str  # "young", "adult", "veteran"

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "gender_presentation": self.gender_presentation,
            "age_bucket": self.age_bucket,
        }

    @classmethod
    def from_dict(cls, d: dict) -> StockFace:
        return cls(
            filename=str(d["filename"]),
            gender_presentation=str(d["gender_presentation"]),
            age_bucket=str(d.get("age_bucket", "adult")),
        )


@dataclass
class StockFacePool:
    """Loads and selects stock faces from a manifest on disk."""

    root: Path
    faces: list[StockFace] = field(default_factory=list)

    @classmethod
    def load(cls, root: Path) -> StockFacePool:
        """Load from ``root/manifest.json``.  Returns an empty pool when
        the manifest is missing or unreadable."""
        root = Path(root)
        manifest_path = root / MANIFEST_FILENAME
        if not manifest_path.exists():
            return cls(root=root)
        try:
            data = json.loads(manifest_path.read_text())
            faces = [StockFace.from_dict(f) for f in data.get("faces", [])]
            # Drop entries whose file is missing on disk.
            faces = [f for f in faces if (root / f.filename).exists()]
            return cls(root=root, faces=faces)
        except (json.JSONDecodeError, OSError, KeyError):
            return cls(root=root)

    def save(self) -> None:
        """Write the manifest to disk."""
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "faces": [f.to_dict() for f in self.faces],
        }
        (self.root / MANIFEST_FILENAME).write_text(
            json.dumps(payload, indent=2)
        )

    def add(self, face: StockFace) -> None:
        self.faces.append(face)

    @property
    def empty(self) -> bool:
        return len(self.faces) == 0

    def select(
        self,
        gender_presentation: str,
        seed: int,
    ) -> Path | None:
        """Pick a stock face matching *gender_presentation*.

        Falls back to any available face when there's no match for the
        requested presentation.  Returns ``None`` when the pool is empty.
        """
        if not self.faces:
            return None
        candidates = [
            f for f in self.faces
            if f.gender_presentation == gender_presentation
        ]
        if not candidates:
            candidates = list(self.faces)
        rng = _random.Random(seed)
        chosen = rng.choice(candidates)
        return self.root / chosen.filename
