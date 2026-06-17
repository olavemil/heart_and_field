#!/usr/bin/env python3
"""Matting + third-person composite proof (Phase 23F).

Cuts spike figures to transparency with rembg and composites a
from-behind player anchor + a frontal DE-style NPC over a real baked
background. Validates three things at once: matte quality on muted vs
white fields, the third-person over-the-shoulder framing, and the
overall read.

    .venv/bin/python scripts/composite_test.py

Outputs matted cutouts + the composite to composite_test/.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "composite_test"
BG = ROOT / "game/assets/backgrounds/bar_modern_modest_warm_p707433/bar/bar__alt0.png"
# Frontal DE NPC (muted cream field — the hard matte) and a from-behind
# standing figure as the player anchor (near-white field — easy matte).
NPC = ROOT / "figure_spike3/front_warm_f_seed3000.png"
PLAYER = ROOT / "figure_spike/interlocutor_tense_seed3000.png"


def main() -> int:
    from PIL import Image
    from rembg import remove

    OUT.mkdir(exist_ok=True)

    def matte(src: Path) -> Image.Image:
        cut = remove(Image.open(src).convert("RGBA"))
        cut.save(OUT / f"matte_{src.stem}.png")
        print(f"matted {src.name} -> matte_{src.stem}.png")
        return cut

    npc = matte(NPC)
    player = matte(PLAYER)

    # Composite over the baked background, canvas = background size.
    bg = Image.open(BG).convert("RGBA")
    W, H = bg.size
    canvas = bg.copy()

    def place(fig: Image.Image, target_h: int, cx: int, bottom: int):
        scale = target_h / fig.height
        fig2 = fig.resize((int(fig.width * scale), target_h), Image.LANCZOS)
        x = cx - fig2.width // 2
        y = bottom - fig2.height
        canvas.alpha_composite(fig2, (max(x, -fig2.width // 3), y))

    # NPC mid-ground, right of centre, facing the player.
    place(npc, target_h=int(H * 0.78), cx=int(W * 0.62), bottom=H)
    # Player anchor: larger, foreground-left, cropped below the frame.
    place(player, target_h=int(H * 1.15), cx=int(W * 0.20), bottom=int(H * 1.05))

    out = OUT / "composite_bar_scene.png"
    canvas.convert("RGB").save(out)
    print(f"composite -> {out.relative_to(ROOT)}  ({W}x{H})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
