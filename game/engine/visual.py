"""Visual pipeline — character rendering and expression overlays (technical §9).

``CharacterVisual.render()`` is the abstraction seam. Ren'Py only calls
this method. The prototype implementation (``_render_flat``) returns a
generated face with a colour-tint overlay. The final implementation
(``_render_composite``, Phase 10) returns a layered composite sprite.

**Swapping prototype → final must not touch any ``.rpy`` file.**

Generation happens at session start or lazily on first scene access —
**never blocking mid-scene**. Fixed seeds per character ID ensure the
same face is always produced. Results are cached to disk.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw

from .characters import Character, TierACharacter, TierBCharacter, TierDSeed
from .comfyui import ComfyUIClient, face_prompt, background_prompt
from .stats import ObservableName, StatName, clamp, stat_value


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Expression(str, Enum):
    """Visual expression derived from observable state."""

    NEUTRAL = "neutral"
    CONFIDENT = "confident"
    DOUBTFUL = "doubtful"
    COMPOSED = "composed"
    AGGRESSIVE = "aggressive"
    WARM = "warm"
    SMUG = "smug"
    RESILIENT = "resilient"
    ANXIOUS = "anxious"


class Pose(str, Enum):
    """Body pose for the character sprite."""

    STANDING = "standing"
    SITTING = "sitting"
    CELEBRATING = "celebrating"
    DEJECTED = "dejected"
    READY = "ready"  # pre-match


# ---------------------------------------------------------------------------
# Expression mapping
# ---------------------------------------------------------------------------

# Map observables to expression enum. The dominant observable (highest value)
# determines the expression.
OBSERVABLE_EXPRESSION_MAP: dict[ObservableName, Expression] = {
    ObservableName.ARROGANCE: Expression.SMUG,
    ObservableName.SELF_DOUBT: Expression.DOUBTFUL,
    ObservableName.COMPOSURE: Expression.COMPOSED,
    ObservableName.COACHABILITY: Expression.NEUTRAL,  # mild expression
    ObservableName.INTIMIDATION: Expression.AGGRESSIVE,
    ObservableName.WARMTH: Expression.WARM,
    ObservableName.CHARISMA: Expression.CONFIDENT,
    ObservableName.RESILIENCE: Expression.RESILIENT,
}


def expression_from_character(
    character: Character,
    mood: float = 0.0,
) -> tuple[Expression, float]:
    """Derive the dominant expression and its intensity from a character.

    Returns ``(expression, intensity)`` where intensity is in ``[0, 1]``.
    If the character is a ``TierDSeed``, returns ``(NEUTRAL, 0.5)``.
    """
    if isinstance(character, TierDSeed):
        return Expression.NEUTRAL, 0.5

    best_expr = Expression.NEUTRAL
    best_val = 0.0

    for obs, expr in OBSERVABLE_EXPRESSION_MAP.items():
        val = character.observable(obs)
        if val > best_val:
            best_val = val
            best_expr = expr

    # Mood override: strong negative mood can push to anxious/dejected.
    if mood < -0.3 and best_val < 0.5:
        best_expr = Expression.ANXIOUS
        best_val = abs(mood)

    return best_expr, clamp(best_val)


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

# Expression-to-tint colour: ``(R, G, B)`` overlay applied at the
# expression's intensity.
EXPRESSION_TINTS: dict[Expression, tuple[int, int, int]] = {
    Expression.NEUTRAL: (200, 200, 200),
    Expression.CONFIDENT: (255, 220, 100),   # warm gold
    Expression.DOUBTFUL: (120, 130, 180),     # cool blue-grey
    Expression.COMPOSED: (180, 210, 190),     # calm green
    Expression.AGGRESSIVE: (220, 100, 100),   # hot red
    Expression.WARM: (240, 200, 160),         # soft amber
    Expression.SMUG: (200, 180, 220),         # purple-ish
    Expression.RESILIENT: (180, 200, 220),    # steel blue
    Expression.ANXIOUS: (160, 160, 190),      # grey-violet
}


@dataclass
class TeamPalette:
    """Colour scheme for a team — used for jersey/kit tinting."""

    primary: tuple[int, int, int] = (30, 60, 180)
    secondary: tuple[int, int, int] = (255, 255, 255)
    accent: tuple[int, int, int] = (200, 50, 50)

    def to_dict(self) -> dict:
        return {
            "primary": list(self.primary),
            "secondary": list(self.secondary),
            "accent": list(self.accent),
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "TeamPalette":
        return cls(
            primary=tuple(d.get("primary", [30, 60, 180])),
            secondary=tuple(d.get("secondary", [255, 255, 255])),
            accent=tuple(d.get("accent", [200, 50, 50])),
        )


# ---------------------------------------------------------------------------
# Sprite layers (Phase 10 composite; stub for now)
# ---------------------------------------------------------------------------


@dataclass
class SpriteLayer:
    """One layer of a composite sprite (Phase 10).

    For Phase 7 prototype, ``layers`` is empty and ``render()`` dispatches
    to ``_render_flat`` instead.

    ``expression`` and ``pose`` are optional filters — if set, the layer
    is only composited when the render call matches. Unset filters mean
    the layer participates in every render.
    """

    name: str  # e.g. "body", "kit", "head", "hair", "expression", "accessory"
    image_path: str | None = None
    tint: tuple[int, int, int] | None = None
    z_order: int = 0
    expression: "Expression | None" = None
    pose: "Pose | None" = None
    tint_strength: float = 0.6  # 0..1; 0 = no tint, 1 = fully replace colour

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "image_path": self.image_path,
            "tint": list(self.tint) if self.tint else None,
            "z_order": self.z_order,
            "expression": self.expression.value if self.expression else None,
            "pose": self.pose.value if self.pose else None,
            "tint_strength": self.tint_strength,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "SpriteLayer":
        return cls(
            name=d["name"],
            image_path=d.get("image_path"),
            tint=tuple(d["tint"]) if d.get("tint") else None,
            z_order=int(d.get("z_order", 0)),
            expression=Expression(d["expression"]) if d.get("expression") else None,
            pose=Pose(d["pose"]) if d.get("pose") else None,
            tint_strength=float(d.get("tint_strength", 0.6)),
        )


# ---------------------------------------------------------------------------
# Face generation spec
# ---------------------------------------------------------------------------


@dataclass
class FaceGenerationSpec:
    """Parameters for generating a character face image.

    Used by the ComfyUI/SD pipeline (when available) or by the
    placeholder generator.
    """

    character_id: str
    seed: int  # deterministic seed derived from character_id
    role: str = "other"
    age_group: str = "adult"  # "youth", "adult", "veteran"
    build: str = "athletic"  # "lean", "athletic", "stocky"
    gender_presentation: str = "masculine"

    @staticmethod
    def seed_from_id(character_id: str) -> int:
        """Deterministic seed from character ID."""
        h = hashlib.sha256(character_id.encode("utf-8")).hexdigest()
        return int(h[:8], 16)

    @classmethod
    def from_character(
        cls,
        character: Character | TierDSeed,
        character_id: str | None = None,
    ) -> "FaceGenerationSpec":
        """Build a spec from a character or seed."""
        if isinstance(character, TierDSeed):
            cid = character_id or f"tier_d_{id(character)}"
            return cls(
                character_id=cid,
                seed=cls.seed_from_id(cid),
                role=character.role.value,
            )
        cid = character.id
        return cls(
            character_id=cid,
            seed=cls.seed_from_id(cid),
            role=character.role.value,
        )

    def to_dict(self) -> dict:
        return {
            "character_id": self.character_id,
            "seed": self.seed,
            "role": self.role,
            "age_group": self.age_group,
            "build": self.build,
            "gender_presentation": self.gender_presentation,
        }


# ---------------------------------------------------------------------------
# CharacterVisual — the main rendering class
# ---------------------------------------------------------------------------

# Default dimensions for generated face images.
FACE_WIDTH = 256
FACE_HEIGHT = 256

# Cache directory relative to the game root.
GENERATED_DIR = "generated"
FACES_DIR = "faces"
OVERLAYS_DIR = "overlays"
BACKGROUNDS_DIR = "backgrounds"


@dataclass
class CharacterVisual:
    """Visual state for a single character.

    Ren'Py calls ``render()`` — it never knows whether this returns a
    flat prototype image or a composite layered sprite.
    """

    character_id: str
    spec: FaceGenerationSpec
    base_face_path: str | None = None
    layers: list[SpriteLayer] = field(default_factory=list)
    _cache_root: Path = field(default_factory=lambda: Path("game") / GENERATED_DIR)
    _comfyui: ComfyUIClient | None = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Public API — Ren'Py only calls this
    # ------------------------------------------------------------------

    def render(
        self,
        expression: Expression = Expression.NEUTRAL,
        intensity: float = 0.5,
        pose: Pose = Pose.STANDING,
    ) -> str:
        """Return a path to the displayable sprite.

        Dispatches to ``_render_composite`` if layers exist, otherwise
        ``_render_flat`` (Phase 7 prototype). Result is cached to disk.
        """
        if self.layers:
            return self._render_composite(expression, intensity, pose)
        return self._render_flat(expression, intensity)

    # ------------------------------------------------------------------
    # Prototype renderer (Phase 7)
    # ------------------------------------------------------------------

    def _render_flat(
        self,
        expression: Expression,
        intensity: float,
    ) -> str:
        """Flat face + colour-tint overlay. Returns path to PNG."""
        cache_path = self._overlay_cache_path(expression, intensity)
        if cache_path.exists():
            return str(cache_path)

        # Load or generate base face.
        base = self._load_or_generate_base()

        # Apply expression tint overlay.
        result = apply_overlay(base, expression, intensity)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(str(cache_path), "PNG")
        return str(cache_path)

    def _render_composite(
        self,
        expression: Expression,
        intensity: float,
        pose: Pose,
    ) -> str:
        """Composite layered sprite (Phase 10).

        Selects layers whose expression/pose filters match the request,
        sorts by ``z_order``, applies per-layer palette tinting, and
        alpha-composites onto a transparent canvas. Result is cached.
        """
        cache_path = self._composite_cache_path(expression, pose, intensity)
        if cache_path.exists():
            return str(cache_path)

        layers = select_layers(self.layers, expression, pose)
        if not layers:
            # Nothing composites for this state — fall back to the flat path
            # so a character never renders as empty.
            return self._render_flat(expression, intensity)

        canvas_size = _layer_canvas_size(layers)
        canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        for layer in layers:
            layer_img = _load_layer_image(layer, canvas_size)
            if layer.tint is not None:
                layer_img = _apply_layer_tint(
                    layer_img, layer.tint, layer.tint_strength
                )
            canvas = Image.alpha_composite(canvas, layer_img)

        # An expression-coloured wash, gentler than the flat path (the
        # expression layer itself already carries most of the mood).
        canvas = apply_overlay(canvas, expression, intensity * 0.5)

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(str(cache_path), "PNG")
        return str(cache_path)

    # ------------------------------------------------------------------
    # Base face management
    # ------------------------------------------------------------------

    def _load_or_generate_base(self) -> Image.Image:
        """Load the base face from cache, or generate via ComfyUI / placeholder."""
        face_path = self._face_cache_path()
        if face_path.exists():
            return Image.open(str(face_path)).convert("RGBA")

        # Try ComfyUI generation first.
        img = self._try_comfyui_face()
        if img is None:
            # Fallback: generate a placeholder face (deterministic from seed).
            img = generate_placeholder_face(self.spec)

        face_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(face_path), "PNG")
        self.base_face_path = str(face_path)
        return img

    def _try_comfyui_face(self) -> Image.Image | None:
        """Attempt to generate a face via ComfyUI. Returns None on failure."""
        if self._comfyui is None or not self._comfyui.enabled:
            return None
        try:
            import io
            prompt = face_prompt(
                role=self.spec.role,
                age_group=self.spec.age_group,
                build=self.spec.build,
                gender_presentation=self.spec.gender_presentation,
            )
            data = self._comfyui.txt2img(
                prompt,
                seed=self.spec.seed,
                width=FACE_WIDTH,
                height=FACE_HEIGHT,
                filename_prefix=f"fh_face_{self.character_id}",
            )
            if data:
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                return img
        except Exception:
            pass
        return None

    def ensure_base_face(self) -> str:
        """Pre-generate and cache the base face. Returns the path.

        Call this at session start for warm-up.
        """
        self._load_or_generate_base()
        path = self._face_cache_path()
        self.base_face_path = str(path)
        return self.base_face_path

    # ------------------------------------------------------------------
    # Cache paths
    # ------------------------------------------------------------------

    def _face_cache_path(self) -> Path:
        return self._cache_root / FACES_DIR / f"{self.character_id}.png"

    def _overlay_cache_path(self, expression: Expression, intensity: float) -> Path:
        # Quantise intensity to avoid explosion of cache entries.
        bucket = int(intensity * 10)
        return (
            self._cache_root
            / OVERLAYS_DIR
            / f"{self.character_id}_{expression.value}_{bucket}.png"
        )

    def _composite_cache_path(
        self, expression: Expression, pose: Pose, intensity: float
    ) -> Path:
        bucket = int(intensity * 10)
        return (
            self._cache_root
            / "composites"
            / f"{self.character_id}_{expression.value}_{pose.value}_{bucket}.png"
        )


# ---------------------------------------------------------------------------
# Composite sprite helpers (Phase 10)
# ---------------------------------------------------------------------------


def select_layers(
    layers: Sequence[SpriteLayer],
    expression: Expression,
    pose: Pose,
) -> list[SpriteLayer]:
    """Return the subset of layers that match this expression + pose.

    Layers with ``expression=None`` and ``pose=None`` are always kept.
    Specific-expression layers only appear when their expression matches;
    if no layer matches the request and a NEUTRAL layer exists, we fall
    back to that so the face is never blank.
    """
    kept: list[SpriteLayer] = []
    any_expression_layer = any(
        layer.expression is not None for layer in layers
    )
    matched_expression = False
    for layer in layers:
        if layer.pose is not None and layer.pose is not pose:
            continue
        if layer.expression is None:
            kept.append(layer)
            continue
        if layer.expression is expression:
            kept.append(layer)
            matched_expression = True

    if any_expression_layer and not matched_expression:
        # Fall back to NEUTRAL expression layers so the sprite isn't blank.
        for layer in layers:
            if layer.expression is Expression.NEUTRAL and (
                layer.pose is None or layer.pose is pose
            ):
                kept.append(layer)

    kept.sort(key=lambda layer: layer.z_order)
    return kept


def _layer_canvas_size(layers: Sequence[SpriteLayer]) -> tuple[int, int]:
    """Size of the composite canvas — max of all layer image sizes."""
    w, h = FACE_WIDTH, FACE_HEIGHT
    for layer in layers:
        if not layer.image_path:
            continue
        p = Path(layer.image_path)
        if not p.exists():
            continue
        try:
            with Image.open(str(p)) as img:
                w = max(w, img.width)
                h = max(h, img.height)
        except Exception:
            continue
    return w, h


def _load_layer_image(
    layer: SpriteLayer, canvas_size: tuple[int, int]
) -> Image.Image:
    """Load a layer image, or produce a solid-colour placeholder of the tint."""
    if layer.image_path and Path(layer.image_path).exists():
        img = Image.open(layer.image_path).convert("RGBA")
        if img.size != canvas_size:
            # Centre-paste onto canvas-sized transparent background.
            bg = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
            ox = (canvas_size[0] - img.width) // 2
            oy = (canvas_size[1] - img.height) // 2
            bg.paste(img, (ox, oy), img)
            return bg
        return img

    # No image — produce a tint-coloured rectangle at full alpha so
    # authored art can be dropped in later without breaking composition.
    tint = layer.tint or (128, 128, 128)
    return Image.new("RGBA", canvas_size, tint + (120,))


def _apply_layer_tint(
    img: Image.Image,
    tint: tuple[int, int, int],
    strength: float,
) -> Image.Image:
    """Blend a tint colour into the image, preserving alpha.

    Strength 0 keeps the original pixels; strength 1 replaces RGB with
    the tint (alpha unchanged). Intended for kit palettes, hair tinting,
    etc. — not the emotion overlay (that's ``apply_overlay``).
    """
    strength = clamp(strength, 0.0, 1.0)
    if strength <= 0.0:
        return img

    rgba = img.convert("RGBA")
    r, g, b, a = rgba.split()
    tint_img = Image.new("RGB", rgba.size, tint)
    blended = Image.blend(Image.merge("RGB", (r, g, b)), tint_img, strength)
    br, bg_, bb = blended.split()
    return Image.merge("RGBA", (br, bg_, bb, a))


# ---------------------------------------------------------------------------
# Procedural layer builder (Tier D and warm-up for Tier B without art)
# ---------------------------------------------------------------------------


# Stock hair / build palette pool — seeded pick by character ID keeps the
# same character visually stable across runs. Authored layer sets replace
# this at the designer's discretion.
_HAIR_COLOURS: list[tuple[int, int, int]] = [
    (30, 20, 10),
    (60, 40, 20),
    (120, 80, 40),
    (200, 180, 100),
    (50, 50, 50),
    (150, 40, 20),
]

_BUILD_TINTS: dict[str, tuple[int, int, int]] = {
    "lean": (190, 170, 150),
    "athletic": (200, 180, 160),
    "stocky": (180, 160, 140),
}


def procedural_layers(
    spec: FaceGenerationSpec,
    palette: TeamPalette | None = None,
) -> list[SpriteLayer]:
    """Build a placeholder-but-structured layer stack from a character spec.

    Lets the composite path run before authored art exists — the character
    still has deterministic body/kit/hair/expression layers. Authored
    content replaces any subset by name.
    """
    import random as _random

    rng = _random.Random(spec.seed)
    palette = palette or TeamPalette()
    hair = rng.choice(_HAIR_COLOURS)
    skin = _BUILD_TINTS.get(spec.build, _BUILD_TINTS["athletic"])

    return [
        SpriteLayer(name="body", tint=skin, z_order=0),
        SpriteLayer(name="kit", tint=palette.primary, z_order=10),
        SpriteLayer(name="hair", tint=hair, z_order=20),
        # Default neutral expression — authored art may add more.
        SpriteLayer(
            name="expression",
            tint=EXPRESSION_TINTS[Expression.NEUTRAL],
            z_order=30,
            expression=Expression.NEUTRAL,
            tint_strength=0.4,
        ),
    ]


# ---------------------------------------------------------------------------
# Placeholder face generator (prototype — replaced by ComfyUI in future)
# ---------------------------------------------------------------------------


def generate_placeholder_face(spec: FaceGenerationSpec) -> Image.Image:
    """Generate a simple deterministic placeholder face from the spec.

    This produces a stylised oval with colour variation based on the
    character's seed. It is NOT the final face generator — ComfyUI / SD
    replaces this when available.
    """
    import random as _random

    rng = _random.Random(spec.seed)

    img = Image.new("RGBA", (FACE_WIDTH, FACE_HEIGHT), (240, 230, 220, 255))
    draw = ImageDraw.Draw(img)

    # Skin tone variation seeded by character.
    r = 180 + rng.randint(-30, 30)
    g = 150 + rng.randint(-30, 30)
    b = 130 + rng.randint(-30, 30)
    skin = (r, g, b, 255)

    # Head oval.
    head_w = 100 + rng.randint(-15, 15)
    head_h = 120 + rng.randint(-15, 15)
    cx, cy = FACE_WIDTH // 2, FACE_HEIGHT // 2 - 10
    draw.ellipse(
        [cx - head_w // 2, cy - head_h // 2, cx + head_w // 2, cy + head_h // 2],
        fill=skin,
        outline=(r - 30, g - 30, b - 30, 255),
        width=2,
    )

    # Eyes.
    eye_y = cy - 10 + rng.randint(-5, 5)
    eye_spacing = 22 + rng.randint(-3, 3)
    eye_r = 6 + rng.randint(-1, 2)
    eye_colour = rng.choice([(60, 40, 20), (40, 80, 40), (30, 50, 90), (50, 50, 50)])
    for ex in [cx - eye_spacing, cx + eye_spacing]:
        draw.ellipse(
            [ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r],
            fill=eye_colour,
        )

    # Mouth — a simple arc.
    mouth_y = cy + 25 + rng.randint(-5, 5)
    mouth_w = 24 + rng.randint(-5, 5)
    draw.arc(
        [cx - mouth_w, mouth_y - 5, cx + mouth_w, mouth_y + 10],
        start=0,
        end=180,
        fill=(r - 40, g - 40, b - 40, 255),
        width=2,
    )

    # Hair — semicircle on top.
    hair_colours = [
        (30, 20, 10),
        (60, 40, 20),
        (120, 80, 40),
        (200, 180, 100),
        (50, 50, 50),
        (150, 40, 20),
    ]
    hair = rng.choice(hair_colours)
    hair_y = cy - head_h // 2 - 5
    draw.ellipse(
        [cx - head_w // 2 - 5, hair_y - 15, cx + head_w // 2 + 5, hair_y + head_h // 3],
        fill=hair + (255,),
    )

    return img


# ---------------------------------------------------------------------------
# Expression overlay
# ---------------------------------------------------------------------------


def apply_overlay(
    base: Image.Image,
    expression: Expression,
    intensity: float,
) -> Image.Image:
    """Apply an expression-coloured overlay to a base face image.

    The overlay is a semi-transparent colour wash that tints the image
    toward the expression's colour palette. Intensity controls opacity.
    """
    result = base.copy()
    tint = EXPRESSION_TINTS.get(expression, (200, 200, 200))
    alpha = int(clamp(intensity, 0.0, 1.0) * 80)  # max 80/255 opacity

    overlay = Image.new("RGBA", result.size, tint + (alpha,))
    result = Image.alpha_composite(result, overlay)
    return result


# ---------------------------------------------------------------------------
# Background generation (stub — ComfyUI deferred)
# ---------------------------------------------------------------------------

BACKGROUND_PROMPTS: dict[str, str] = {
    "locker_room": "football locker room interior, dramatic lighting, sports atmosphere",
    "training_ground": "outdoor training pitch, morning light, football equipment",
    "stadium": "football stadium interior, match day, crowd in background",
    "pub": "quiet british pub interior, warm lighting, evening",
    "home": "modest apartment living room, evening light, personal items",
    "press_room": "press conference room, microphones, bright lights",
    "treatment_room": "physiotherapy room, clinical lighting, treatment table",
    "bus": "team bus interior, motorway, evening light through windows",
}


def get_background(
    location: str,
    cache_root: Path | None = None,
    comfyui: ComfyUIClient | None = None,
) -> str | None:
    """Return a path to a background image, generating if needed.

    Returns ``None`` if the location is unknown or generation is
    unavailable. Ren'Py falls back to its default background.
    """
    root = cache_root or Path("game") / GENERATED_DIR
    cache_path = root / BACKGROUNDS_DIR / f"{location}.png"

    if cache_path.exists():
        return str(cache_path)

    if location not in BACKGROUND_PROMPTS:
        return None

    # Try ComfyUI generation first.
    img = _try_comfyui_background(location, comfyui)
    if img is None:
        # Fallback: simple gradient placeholder.
        img = _generate_placeholder_background(location)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(cache_path), "PNG")
    return str(cache_path)


def _try_comfyui_background(
    location: str, comfyui: ComfyUIClient | None
) -> Image.Image | None:
    """Attempt to generate a background via ComfyUI."""
    if comfyui is None or not comfyui.enabled:
        return None
    try:
        import io
        prompt = background_prompt(location)
        data = comfyui.txt2img(
            prompt,
            seed=hash(location) & 0xFFFFFFFF,
            width=800,
            height=600,
            filename_prefix=f"fh_bg_{location}",
        )
        if data:
            return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        pass
    return None


def _generate_placeholder_background(location: str) -> Image.Image:
    """Simple gradient background as placeholder."""
    import random as _random

    rng = _random.Random(location)
    width, height = 800, 600

    # Choose colours based on location hash.
    r1 = rng.randint(30, 100)
    g1 = rng.randint(30, 100)
    b1 = rng.randint(40, 120)
    r2 = rng.randint(100, 200)
    g2 = rng.randint(100, 200)
    b2 = rng.randint(100, 200)

    img = Image.new("RGB", (width, height))
    for y in range(height):
        t = y / height
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        for x in range(width):
            img.putpixel((x, y), (r, g, b))

    return img


# ---------------------------------------------------------------------------
# Visual manager — orchestrates visuals for all characters
# ---------------------------------------------------------------------------


@dataclass
class VisualManager:
    """Manages ``CharacterVisual`` instances for the session.

    Handles warm-up, lazy generation, and Tier D pool management.
    """

    visuals: dict[str, CharacterVisual] = field(default_factory=dict)
    cache_root: Path = field(default_factory=lambda: Path("game") / GENERATED_DIR)
    comfyui: ComfyUIClient | None = None

    def get_visual(
        self,
        character: Character | TierDSeed,
        character_id: str | None = None,
    ) -> CharacterVisual:
        """Get or create a ``CharacterVisual`` for a character.

        Lazy: creates the visual on first access and caches the base face.
        """
        if isinstance(character, TierDSeed):
            cid = character_id or f"tier_d_{id(character)}"
        else:
            cid = character.id

        if cid in self.visuals:
            return self.visuals[cid]

        spec = FaceGenerationSpec.from_character(character, cid)
        visual = CharacterVisual(
            character_id=cid,
            spec=spec,
            _cache_root=self.cache_root,
            _comfyui=self.comfyui,
        )
        self.visuals[cid] = visual
        return visual

    def warm_up(self, characters: dict[str, Character]) -> None:
        """Pre-generate base faces for all named characters.

        Call at session start so rendering never blocks mid-scene.
        """
        for cid, char in characters.items():
            visual = self.get_visual(char)
            visual.ensure_base_face()

    def populate_procedural_layers(
        self,
        characters: dict[str, Character],
        palette: TeamPalette | None = None,
    ) -> None:
        """Give named characters a procedural layer stack.

        Lets the composite path run before authored sprite art exists.
        Authored ``CharacterVisual.layers`` set directly will not be
        overwritten.
        """
        for char in characters.values():
            visual = self.get_visual(char)
            if visual.layers:
                continue
            visual.layers = procedural_layers(visual.spec, palette)

    def render_character(
        self,
        character: Character | TierDSeed,
        expression: Expression | None = None,
        intensity: float | None = None,
        mood: float = 0.0,
        pose: Pose = Pose.STANDING,
        character_id: str | None = None,
    ) -> str:
        """High-level render: derive expression if not given, then render.

        This is the method Ren'Py display labels should call.
        """
        visual = self.get_visual(character, character_id)

        if expression is None or intensity is None:
            expr, inten = expression_from_character(character, mood)
            expression = expression or expr
            intensity = intensity if intensity is not None else inten

        return visual.render(expression, intensity, pose)

    def render_background(self, location: str) -> str | None:
        """Render a background image for a location."""
        return get_background(location, self.cache_root, self.comfyui)
