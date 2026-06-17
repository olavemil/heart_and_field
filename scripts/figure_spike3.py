#!/usr/bin/env python3
"""Figure spike v3 — Disco Elysium-style FRONTAL with vague faces.

v1/v2 protected faces by framing (from behind / turned away). This
explores the opposite per the DE reference: figures FACING the viewer
with the face present but a loose impressionistic *suggestion* — painted
sketch, not rendered detail. The negative pushes away from photoreal /
sharp faces rather than from faces entirely, so we land the DE middle
ground instead of either a full face or an eerie void.

Writes to figure_spike3/ for comparison with v1/v2.

    .venv/bin/python scripts/figure_spike3.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "game"))

from engine.comfyui import ComfyUIClient, _sd3_txt2img_workflow  # noqa: E402

OUT = ROOT / "figure_spike3"

# Disco Elysium-ish: oil-and-ink painted sketch, loose, faces suggested.
STYLE = (
    "Disco Elysium style painted character study, loose oil and ink "
    "sketch, thick visible brushstrokes, gestural sketchy linework, "
    "impressionistic abstracted face with soft indistinct blurred "
    "features, unfinished painterly sketch, muted desaturated palette, "
    "moody, full body, plain muted background"
)
NEGATIVE = (
    "photorealistic, photograph, smooth skin, sharp focus, detailed eyes, "
    "detailed rendered face, glamour, beauty shot, anime, cartoon, clean "
    "lines, 3d render, cgi, pixel art, text, watermark, deformed, extra "
    "limbs, extra fingers"
)

FIGURES = {
    "front_warm_f": (
        "a woman with dark skin and long dark hair, facing the viewer, "
        "warm open relaxed posture, slight smile, casual clothes"
    ),
    "front_tense_m": (
        "a man with light skin and short blonde hair, facing the viewer, "
        "arms crossed, guarded tense posture, casual clothes"
    ),
    "front_manager_m": (
        "an older man in a tracksuit, facing the viewer, stern arms-folded "
        "posture, football coach"
    ),
    "front_player_f": (
        "a young woman athlete in a tracksuit, facing the viewer, relaxed "
        "confident posture"
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=1216)
    ap.add_argument("--steps", type=int, default=34)
    ap.add_argument("--cfg", type=float, default=4.5)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = ComfyUIClient(timeout=args.timeout)
    if not args.dry_run and not client.is_available():
        print("ComfyUI not reachable at", client.base_url, file=sys.stderr)
        return 1

    OUT.mkdir(exist_ok=True)
    for label, subject in FIGURES.items():
        prompt = f"{subject}, {STYLE}"
        if args.dry_run:
            print(f"\n=== {label} ===\n{prompt}")
            continue
        seed = 3000
        wf = _sd3_txt2img_workflow(
            prompt, negative_prompt=NEGATIVE, seed=seed,
            width=args.width, height=args.height, steps=args.steps,
            cfg=args.cfg, denoise=1.0, filename_prefix=f"fig3_{label}",
        )
        data = client._submit_and_wait(wf)
        if data is None:
            print(f"{label}: FAILED")
            continue
        out = OUT / f"{label}_seed{seed}.png"
        out.write_bytes(data)
        print(f"{label}: {out.relative_to(ROOT)} ({len(data)//1024} KB)")
    print(f"\nDone. Inspect PNGs in {OUT.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
