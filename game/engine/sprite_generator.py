"""Two-step sprite generator: neutral first, variants second.

Step 1: text-to-image from descriptor → neutral portrait.
Step 2: image-to-image with the neutral as input → one variant per
expression, with a prompt that describes the expression only.

Keeping the neutral image as the img2img input anchors identity across
variants. A proper identity-preservation adapter (IP-Adapter / InstantID)
improves this significantly; when one is not wired in, keeping
``variant_denoise`` low (~0.35) holds the face close at the cost of
expression range.

Background removal is wired through a pluggable callable — pass
``rembg.remove`` (or any equivalent) via ``bg_remover``. When omitted,
the saved image keeps whatever background ComfyUI produced.

The generator never hides errors: a ComfyUI failure raises
``SpriteGenerationError`` so the CLI can surface it. Falling back to a
placeholder is the runtime path's job, not the asset-generation path's.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image

from .comfyui import ComfyUIClient
from .sprite_pool import CharacterDescriptor, SpriteEntry, SpriteManifest


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SpriteGenerationError(RuntimeError):
    """Raised when a generation step fails and cannot produce an image."""


# ---------------------------------------------------------------------------
# Expression prompts
# ---------------------------------------------------------------------------


# The set of expressions the generator produces by default. Matches the
# ``Expression`` enum in ``visual.py`` (stringly typed here to avoid a
# layering dependency — descriptors and expressions are orthogonal).
DEFAULT_EXPRESSIONS: tuple[str, ...] = (
    "neutral",
    "confident",
    "doubtful",
    "composed",
    "aggressive",
    "warm",
    "anxious",
)

EXPRESSION_PROMPTS: dict[str, str] = {
    "neutral": (
        "relaxed neutral expression, mouth closed, lips together, "
        "level gaze straight at camera, brows relaxed and even"
    ),
    "confident": (
        "confident expression, slight closed-mouth smile with corners up, "
        "chin tilted up slightly, steady direct gaze, one eyebrow "
        "raised, jaw relaxed"
    ),
    "doubtful": (
        "skeptical doubtful expression, one brow raised, "
        "eyes narrowed with slight squint, lips pressed thin, "
        "head tilted slightly to one side"
    ),
    "composed": (
        "calm composed expression, soft steady eyes looking straight ahead, "
        "mouth slightly open, brows smooth and level, "
        "slight tension in jaw showing focus"
    ),
    "aggressive": (
        "angry aggressive expression, brows furrowed sharply downward, "
        "upper lip curled showing teeth, nostrils flared, "
        "jaw clenched tight, chin dropped, intense glare from under brows"
    ),
    "warm": (
        "warm friendly expression, broad genuine smile showing teeth, "
        "crow's feet crinkle at eye corners, raised cheeks, "
        "relaxed open brows, soft eyes"
    ),
    "smug": (
        "smug expression, asymmetric smirk pulling one mouth corner up, "
        "one eyebrow raised high, half-lidded eyes, "
        "chin tilted up, knowing look"
    ),
    "resilient": (
        "determined resilient expression, lips pressed firmly together, "
        "jaw set, brows level but low, focused forward stare, "
        "slight nostril flare, neck muscles taut"
    ),
    "anxious": (
        "anxious worried expression, brows raised and raised in centre, "
        "eyes wide and glancing down-left, lower lip bitten, "
        "forehead creased, shoulders tense and raised"
    ),
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class SpriteGenerationConfig:
    """Tunables for the two-step generation."""

    # Image dimensions the model is asked for. Downstream composite layers
    # paste this onto their own canvas size.
    width: int = 768
    height: int = 768

    # Neutral-face generation.
    neutral_steps: int = 28
    neutral_cfg: float = 4.5

    # Variant img2img.
    variant_steps: int = 20
    variant_cfg: float = 4.5
    # Low denoise keeps identity; raise carefully if expressions look too muted.
    variant_denoise: float = 0.50

    base_prompt_prefix: str = (
        "professional close-up portrait painting, full head and shoulders only, painterly style,"
    )
    base_prompt_suffix: str = (
        ", plain neutral grey background, soft studio lighting, "
        "sharp focus on face, natural skin texture, shot on 85mm lens, "
        "wearing plain dark crew-neck shirt, exaggerated facial expressions, "
        "entire head including hair"
    )

    negative_prompt: str = (
        "distorted face, artifcating, poorly done, "
        "extra limbs, blurry, low quality, watermark, text, logo, "
        "badge, emblem, crest, coat of arms, flag, jersey number, "
        "uniform details, nipples, bare chest, shirtless, nsfw, bored, unreadable"
    )


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


BgRemover = Callable[[bytes], bytes]


@dataclass
class SpriteGenerator:
    """Orchestrates descriptor → neutral → variants → manifest updates."""

    client: ComfyUIClient
    manifest: SpriteManifest
    config: SpriteGenerationConfig = field(default_factory=SpriteGenerationConfig)
    bg_remover: BgRemover | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_set(
        self,
        descriptor: CharacterDescriptor,
        *,
        expressions: Iterable[str] = DEFAULT_EXPRESSIONS,
        seed: int | None = None,
        reserved_for: str | None = None,
    ) -> SpriteEntry:
        """Produce a complete sprite set (neutral + variants) and register it.

        ``seed`` makes the run reproducible; when omitted, a hash of the
        bucket key is used so regenerating the same descriptor twice
        yields the same sprite.
        """
        entry_id = self.manifest.next_entry_id(descriptor)
        if seed is None:
            seed = int(descriptor.short_hash(), 16)

        bucket_dir = Path(descriptor.bucket_key()) / entry_id
        abs_dir = self.manifest.assets_root / bucket_dir
        abs_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: neutral.
        neutral_rel = str(bucket_dir / "neutral.png")
        neutral_abs = self.manifest.assets_root / neutral_rel
        self._generate_neutral(descriptor, seed, out_path=neutral_abs)

        entry = SpriteEntry(
            entry_id=entry_id,
            descriptor=descriptor,
            neutral_path=neutral_rel,
            variants={"neutral": neutral_rel},
            reserved_for=reserved_for,
        )

        # Step 2: variants conditioned on the neutral.
        # Upload the neutral to ComfyUI once so every variant references it.
        with open(neutral_abs, "rb") as fh:
            neutral_bytes = fh.read()
        uploaded_name = self.client.upload_image(
            neutral_bytes, filename=f"fh_neutral_{entry_id}.png"
        )
        if not uploaded_name:
            raise SpriteGenerationError(
                f"failed to upload neutral to ComfyUI for {entry_id!r}"
            )

        for expr in expressions:
            if expr == "neutral":
                continue
            rel = str(bucket_dir / f"{expr}.png")
            abs_path = self.manifest.assets_root / rel
            self._generate_variant(
                descriptor=descriptor,
                expression=expr,
                input_image=uploaded_name,
                seed=seed + _expr_seed_offset(expr),
                out_path=abs_path,
            )
            entry.variants[expr] = rel

        self.manifest.add_entry(entry)
        self.manifest.save()
        return entry

    # ------------------------------------------------------------------
    # Step 1 — neutral
    # ------------------------------------------------------------------

    def _generate_neutral(
        self,
        descriptor: CharacterDescriptor,
        seed: int,
        out_path: Path,
    ) -> None:
        prompt = (
            self.config.base_prompt_prefix
            + descriptor.to_prompt_fragment()
            + ", "
            + EXPRESSION_PROMPTS["neutral"]
            + self.config.base_prompt_suffix
        )
        data = self.client.txt2img(
            prompt,
            seed=seed,
            width=self.config.width,
            height=self.config.height,
            steps=self.config.neutral_steps,
            cfg=self.config.neutral_cfg,
            filename_prefix=f"fh_neutral_{descriptor.short_hash()}",
        )
        if not data:
            raise SpriteGenerationError(
                f"neutral generation returned no data for {descriptor.bucket_key()!r}"
            )
        self._save_image(data, out_path)

    # ------------------------------------------------------------------
    # Step 2 — variant
    # ------------------------------------------------------------------

    def _generate_variant(
        self,
        descriptor: CharacterDescriptor,
        expression: str,
        input_image: str,
        seed: int,
        out_path: Path,
    ) -> None:
        expr_prompt = EXPRESSION_PROMPTS.get(
            expression, f"{expression} expression"
        )
        prompt = (
            self.config.base_prompt_prefix
            + descriptor.to_prompt_fragment()
            + ", "
            + expr_prompt
            + self.config.base_prompt_suffix
        )
        data = self.client.img2img(
            prompt,
            input_image=input_image,
            seed=seed,
            width=self.config.width,
            height=self.config.height,
            steps=self.config.variant_steps,
            cfg=self.config.variant_cfg,
            denoise=self.config.variant_denoise,
            filename_prefix=f"fh_var_{descriptor.short_hash()}_{expression}",
        )
        if not data:
            raise SpriteGenerationError(
                f"variant {expression!r} returned no data for "
                f"{descriptor.bucket_key()!r}"
            )
        self._save_image(data, out_path)

    # ------------------------------------------------------------------
    # Shared — save with optional bg-remove
    # ------------------------------------------------------------------

    def _save_image(self, data: bytes, out_path: Path) -> None:
        if self.bg_remover is not None:
            try:
                data = self.bg_remover(data)
            except Exception as exc:
                log.warning("bg_remover failed (%s) — keeping original", exc)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Normalise to RGBA PNG so downstream compositing can assume alpha.
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img.save(str(out_path), "PNG")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expr_seed_offset(expression: str) -> int:
    """Deterministic seed offset per expression so variants don't collide."""
    import hashlib

    h = hashlib.sha256(expression.encode("utf-8")).hexdigest()
    return int(h[:4], 16)
