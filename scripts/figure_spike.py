#!/usr/bin/env python3
"""Face-less figure quality spike (Phase 23F).

Throwaway: validate that abstract, face-less painterly figures read as
expressive rather than eerie, that coarse appearance axes read as
distinct people, and that posture conveys tone without a face — before
committing to the ~150-asset catalogue (field_and_heart_figure_assets.md).

Reuses the validated painterly recipe (euler/sgm_uniform, 32 steps) plus
a face/detail negative prompt. Portrait field; matting to transparency is
a later integration step, not a quality question here.

    .venv/bin/python scripts/figure_spike.py            # all, 1 seed
    .venv/bin/python scripts/figure_spike.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "game"))

from engine.comfyui import ComfyUIClient, _sd3_txt2img_workflow  # noqa: E402

OUT = ROOT / "figure_spike"

STYLE = (
    "loose painterly digital painting, impressionistic, soft visible "
    "brushwork, muted natural palette, soft focus, expressive full-body "
    "figure, gestural, plain neutral background, faceless, face turned "
    "away, no visible face"
)
NEGATIVE = (
    "face, facial features, eyes, mouth, portrait, close-up, identifiable "
    "person, detailed face, detailed hands, pixel art, 3d render, cgi, "
    "photorealistic, text, watermark, deformed, extra limbs, sharp hard "
    "edges, low quality"
)

# (label, subject) — spread across the catalogue's trickiest cases.
FIGURES = {
    "interlocutor_warm": (
        "a woman with dark skin and long dark hair, seated, leaning in, "
        "open attentive warm posture, casual clothes"
    ),
    "interlocutor_tense": (
        "a man with light skin and short blonde hair, arms crossed, "
        "turned away, tense closed guarded posture, casual clothes"
    ),
    "manager_angry": (
        "an older man in a tracksuit, pointing and berating, "
        "condescending angry posture, football coach"
    ),
    "manager_warm": (
        "a woman in a tracksuit, arms open, encouraging and comforting, "
        "warm posture, football coach"
    ),
    "player_motion_soccer": (
        "a woman soccer player in motion, running with the ball, dynamic "
        "athletic action, sports kit"
    ),
    "doctor": (
        "a woman doctor in a white coat, standing, calm professional "
        "posture, stethoscope"
    ),
    "waitress": (
        "a waitress in an apron carrying a tray, mid-step, cafe staff"
    ),
    "player_silhouette": (
        "a single person seen from behind, foreground silhouette, "
        "simple coloured outline, anonymous, standing, minimal"
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=1216)
    ap.add_argument("--steps", type=int, default=32)
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
        for s in range(args.seeds):
            seed = 3000 + s
            wf = _sd3_txt2img_workflow(
                prompt, negative_prompt=NEGATIVE, seed=seed,
                width=args.width, height=args.height, steps=args.steps,
                cfg=args.cfg, denoise=1.0, filename_prefix=f"fig_{label}",
            )
            data = client._submit_and_wait(wf)
            if data is None:
                print(f"{label} seed {seed}: FAILED")
                continue
            out = OUT / f"{label}_seed{seed}.png"
            out.write_bytes(data)
            print(f"{label} seed {seed}: {out.relative_to(ROOT)} ({len(data)//1024} KB)")
    print(f"\nDone. Inspect PNGs in {OUT.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
