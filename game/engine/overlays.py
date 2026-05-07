"""Noise overlay pipeline (addendum §1.2).

The ATL composite stacks one or more noise overlays on top of the
variant-crossfade background and the colour grades. Overlays are static
PNGs with alpha; ATL drives the scroll / pulse animation.

This module contains:

- ``NoiseOverlay`` and ``OverlayAnim`` enums (verbatim from the addendum).
- ``OverlaySpec`` records bundling path + alpha + animation + speed.
- ``OVERLAY_SPECS`` lookup keyed by ``NoiseOverlay``.
- ``LOCATION_OVERLAYS`` thin bridge from our existing ``LocationKind``
  to the overlay stack — full ``SceneType`` taxonomy is deferred to
  Phase 16.
- ``overlays_for(kind, atmosphere)`` pure function merging the
  scene-kind base stack with weather/time-conditional additions.
- ``generate_overlay_pngs(...)`` writes the procedural noise textures
  to disk with a simple version-keyed cache.

Design rules:

- All overlay generation is deterministic given an injected seed —
  no module-level RNG.
- PNG paths in ``OverlaySpec`` are *relative* to the overlays dir; the
  session resolves them against ``overlays_root``.
- Overlays compose multiplicatively at low alpha; never stack the same
  ``NoiseOverlay`` twice (the merge function deduplicates).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .background_pool import LocationKind
from .color_grades import SceneAtmosphere, TimeOfDay, Weather


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NoiseOverlay(str, Enum):
    FILM_GRAIN = "film_grain"
    LIGHT_DUST = "light_dust"
    HEAT_SHIMMER = "heat_shimmer"
    RAIN_STREAK = "rain_streak"
    CROWD_BLUR = "crowd_blur"


class OverlayAnim(str, Enum):
    SCROLL_RANDOM = "scroll_random"
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"
    PULSE = "pulse"
    STATIC = "static"


# ---------------------------------------------------------------------------
# OverlaySpec + lookup table (addendum §1.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OverlaySpec:
    """Authored properties for one overlay layer."""

    overlay: NoiseOverlay
    path: str  # relative to overlays_root
    alpha: float
    animation: OverlayAnim
    speed: float


OVERLAY_SPECS: dict[NoiseOverlay, OverlaySpec] = {
    NoiseOverlay.FILM_GRAIN: OverlaySpec(
        NoiseOverlay.FILM_GRAIN, "grain.png", 0.06,
        OverlayAnim.SCROLL_RANDOM, 0.5,
    ),
    NoiseOverlay.LIGHT_DUST: OverlaySpec(
        NoiseOverlay.LIGHT_DUST, "dust.png", 0.12,
        OverlayAnim.SCROLL_UP, 0.3,
    ),
    NoiseOverlay.HEAT_SHIMMER: OverlaySpec(
        NoiseOverlay.HEAT_SHIMMER, "shimmer.png", 0.10,
        OverlayAnim.PULSE, 0.2,
    ),
    NoiseOverlay.RAIN_STREAK: OverlaySpec(
        NoiseOverlay.RAIN_STREAK, "rain.png", 0.20,
        OverlayAnim.SCROLL_DOWN, 0.8,
    ),
    NoiseOverlay.CROWD_BLUR: OverlaySpec(
        NoiseOverlay.CROWD_BLUR, "crowd.png", 0.15,
        OverlayAnim.SCROLL_RANDOM, 0.4,
    ),
}


# ---------------------------------------------------------------------------
# Scene-kind → overlays
# ---------------------------------------------------------------------------


# Thin bridge mapping our existing ``LocationKind`` enum to a base
# overlay stack. The full ``SceneType`` taxonomy from the addendum is
# deferred to Phase 16 — when that lands, this table moves to be keyed
# by ``SceneType`` and gets per-instance refinements.
LOCATION_OVERLAYS: dict[LocationKind, tuple[NoiseOverlay, ...]] = {
    LocationKind.SUBURBAN_HOUSE: (NoiseOverlay.FILM_GRAIN, NoiseOverlay.LIGHT_DUST),
    LocationKind.APARTMENT:      (NoiseOverlay.FILM_GRAIN, NoiseOverlay.LIGHT_DUST),
    LocationKind.SCHOOL:         (NoiseOverlay.FILM_GRAIN,),
    LocationKind.GYM:            (NoiseOverlay.FILM_GRAIN,),
    LocationKind.LOCKER_ROOM:    (NoiseOverlay.FILM_GRAIN, NoiseOverlay.LIGHT_DUST),
    LocationKind.NEIGHBORHOOD:   (NoiseOverlay.FILM_GRAIN,),
    LocationKind.CAFE:           (NoiseOverlay.FILM_GRAIN, NoiseOverlay.LIGHT_DUST),
    LocationKind.PARK:           (NoiseOverlay.FILM_GRAIN,),
    LocationKind.STADIUM:        (NoiseOverlay.FILM_GRAIN, NoiseOverlay.CROWD_BLUR),
}


# Outdoor-ish location kinds get heat shimmer in clear midday weather.
# Indoor scenes don't, even when it's bright outside — the shimmer would
# read as a generation artefact rather than weather.
_OUTDOOR_KINDS: frozenset[LocationKind] = frozenset({
    LocationKind.NEIGHBORHOOD,
    LocationKind.PARK,
    LocationKind.STADIUM,
})


def _base_overlays(kind: LocationKind) -> tuple[NoiseOverlay, ...]:
    """The scene-kind's authored overlay stack. Defaults to grain only
    for unmapped kinds so future enum additions don't render bare."""
    return LOCATION_OVERLAYS.get(kind, (NoiseOverlay.FILM_GRAIN,))


def overlays_for(
    kind: LocationKind, atmosphere: SceneAtmosphere
) -> list[OverlaySpec]:
    """Merge the scene-kind base stack with weather/time additions.

    Order matters for compositing: returned overlays should be drawn
    bottom-to-top in the listed order. Grain always lands first;
    weather streaks land on top so they read above dust.
    """
    selected: list[NoiseOverlay] = list(_base_overlays(kind))

    # Rain weather: add the rain streak overlay on top.
    if atmosphere.weather == Weather.RAIN and NoiseOverlay.RAIN_STREAK not in selected:
        selected.append(NoiseOverlay.RAIN_STREAK)

    # Heat shimmer: only outdoor scenes during clear midday/afternoon.
    is_outdoor = kind in _OUTDOOR_KINDS
    is_hot_clear = (
        atmosphere.weather == Weather.CLEAR
        and atmosphere.time_of_day in (TimeOfDay.MIDDAY, TimeOfDay.AFTERNOON)
    )
    if is_outdoor and is_hot_clear and NoiseOverlay.HEAT_SHIMMER not in selected:
        selected.append(NoiseOverlay.HEAT_SHIMMER)

    return [OVERLAY_SPECS[ov] for ov in selected]


# ---------------------------------------------------------------------------
# Procedural PNG generation
# ---------------------------------------------------------------------------


# Bump when any generator changes so existing dirs regenerate without
# manual cleanup.
OVERLAY_GENERATOR_VERSION = "v1"

_VERSION_FILENAME = "_version.json"
_OVERLAY_SIZE = 512


def generate_overlay_pngs(
    overlays_dir: Path,
    *,
    size: int = _OVERLAY_SIZE,
    seed_base: int = 0xF1E1D,
) -> dict[NoiseOverlay, Path]:
    """Render every overlay's PNG into ``overlays_dir``.

    Idempotent — skips work when the on-disk version marker matches and
    every expected file is present. Returns a ``{NoiseOverlay: Path}``
    map of absolute paths.
    """
    overlays_dir = Path(overlays_dir)
    overlays_dir.mkdir(parents=True, exist_ok=True)
    version_path = overlays_dir / _VERSION_FILENAME

    paths: dict[NoiseOverlay, Path] = {
        ov: overlays_dir / spec.path
        for ov, spec in OVERLAY_SPECS.items()
    }

    cached: dict | None = None
    if version_path.exists():
        try:
            cached = json.loads(version_path.read_text())
        except (json.JSONDecodeError, OSError):
            cached = None
    all_present = all(p.exists() for p in paths.values())
    if (
        cached is not None
        and cached.get("version") == OVERLAY_GENERATOR_VERSION
        and all_present
    ):
        return paths

    _render_grain(paths[NoiseOverlay.FILM_GRAIN], size, seed_base + 1)
    _render_dust(paths[NoiseOverlay.LIGHT_DUST], size, seed_base + 2)
    _render_shimmer(paths[NoiseOverlay.HEAT_SHIMMER], size, seed_base + 3)
    _render_rain(paths[NoiseOverlay.RAIN_STREAK], size, seed_base + 4)
    _render_crowd(paths[NoiseOverlay.CROWD_BLUR], size, seed_base + 5)

    version_path.write_text(json.dumps({
        "version": OVERLAY_GENERATOR_VERSION,
        "size": size,
        "seed_base": seed_base,
    }, indent=2))
    return paths


def overlay_path(overlays_dir: Path, overlay: NoiseOverlay) -> Path:
    """Resolve the absolute PNG path for a single overlay."""
    return Path(overlays_dir) / OVERLAY_SPECS[overlay].path


# --- Generators ------------------------------------------------------------
#
# All generators take a deterministic seed and write an RGBA PNG of the
# given square size. The textures are deliberately simple — they are
# placeholders the artist can replace with hand-painted assets without
# any code change. The ATL composite drives the actual motion.


def _render_grain(out_path: Path, size: int, seed: int) -> None:
    """Fine white-noise grain at low alpha — used in every scene."""
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed)
    noise = rng.integers(80, 220, (size, size), dtype=np.uint8)
    alpha = rng.integers(40, 110, (size, size), dtype=np.uint8)
    rgba = np.stack([noise, noise, noise, alpha], axis=-1)
    Image.fromarray(rgba, "RGBA").save(str(out_path), "PNG")


def _render_dust(out_path: Path, size: int, seed: int) -> None:
    """Sparse small bright motes on a transparent background."""
    import numpy as np
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    rng = np.random.default_rng(seed)
    n_motes = size // 2
    for _ in range(n_motes):
        x = int(rng.integers(0, size))
        y = int(rng.integers(0, size))
        r = int(rng.integers(1, 4))
        a = int(rng.integers(40, 140))
        draw.ellipse((x - r, y - r, x + r, y + r),
                     fill=(255, 245, 220, a))
    img.save(str(out_path), "PNG")


def _render_shimmer(out_path: Path, size: int, seed: int) -> None:
    """Low-frequency wavy luminance — heat haze placeholder."""
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed)
    coarse = rng.standard_normal((size // 16, size // 16))
    # Bilinear upsample by repeating + blending edges via PIL resize.
    span = max(coarse.max() - coarse.min(), 1e-9)
    upsampled = Image.fromarray(
        ((coarse - coarse.min()) / span * 255).astype("uint8"),
        "L",
    ).resize((size, size), Image.BILINEAR)
    arr = np.asarray(upsampled, dtype=np.uint8)
    # Map luminance to alpha so brighter ripples are more visible.
    alpha = (arr.astype(np.float32) * 0.4).clip(0, 90).astype(np.uint8)
    rgba = np.stack([arr, arr, arr, alpha], axis=-1)
    Image.fromarray(rgba, "RGBA").save(str(out_path), "PNG")


def _render_rain(out_path: Path, size: int, seed: int) -> None:
    """Vertical streaks at a slight angle, mostly transparent."""
    import numpy as np
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    rng = np.random.default_rng(seed)
    n_streaks = size
    for _ in range(n_streaks):
        x = int(rng.integers(0, size))
        y = int(rng.integers(-20, size))
        length = int(rng.integers(8, 28))
        # 5° lean for parallax feel.
        x2 = x + 2
        y2 = y + length
        a = int(rng.integers(80, 180))
        draw.line((x, y, x2, y2), fill=(180, 200, 230, a), width=1)
    img.save(str(out_path), "PNG")


def _render_crowd(out_path: Path, size: int, seed: int) -> None:
    """Mottled medium-frequency noise — suggests crowd blur in stadium."""
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed)
    coarse = rng.integers(60, 200, (size // 4, size // 4), dtype=np.uint8)
    upsampled = Image.fromarray(coarse, "L").resize(
        (size, size), Image.BILINEAR,
    )
    arr = np.asarray(upsampled, dtype=np.uint8)
    alpha = ((arr.astype(np.int16) - 100).clip(0, 90)).astype(np.uint8)
    rgba = np.stack([arr, arr, arr, alpha], axis=-1)
    Image.fromarray(rgba, "RGBA").save(str(out_path), "PNG")
