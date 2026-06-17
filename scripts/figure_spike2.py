#!/usr/bin/env python3
"""Face-less figure spike v2 — stronger painterly + face protection.

v1 verdict: good, but front-facing/action poses leaked faces (soccer
player, angry manager) and the style could be looser. v2 pushes the
abstraction harder so even a visible face dissolves into brushwork, and
reinforces face protection through framing (from behind / turned away)
plus a stronger negative.

Writes to figure_spike2/ for side-by-side comparison with v1.

    .venv/bin/python scripts/figure_spike2.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "game"))

from engine.comfyui import ComfyUIClient, _sd3_txt2img_workflow  # noqa: E402

OUT = ROOT / "figure_spike2"

STYLE = (
    "very loose impressionistic oil painting, abstract gestural brushwork, "
    "palette-knife strokes, simplified blocky forms, soft blurred edges, "
    "the figure suggested rather than detailed, face dissolved into loose "
    "brushstrokes, seen from behind or in profile with head turned away, "
    "anonymous, muted palette, plain neutral background, alla prima"
)
NEGATIVE = (
    "face, facial features, eyes, mouth, nose, portrait, close-up, looking "
    "at viewer, front view, facing camera, detailed face, rendered face, "
    "identifiable person, sharp focus, fine detail, crisp lines, detailed "
    "hands, photorealistic, photograph, 3d render, cgi, pixel art, text, "
    "watermark, deformed, extra limbs"
)

# Focus on the cases v1 struggled with + one control (warm interlocutor).
FIGURES = {
    "interlocutor_warm": (
        "a woman with dark skin and long dark hair, seated, leaning in, "
        "open attentive warm posture, casual clothes"
    ),
    "manager_angry": (
        "an older man in a tracksuit, pointing and berating, "
        "condescending angry posture, football coach, seen from behind"
    ),
    "player_motion_soccer": (
        "a woman soccer player running with the ball, dynamic athletic "
        "action, sports kit, seen from behind, running away"
    ),
    "doctor": (
        "a woman doctor in a white coat, standing, calm professional "
        "posture, stethoscope"
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
            cfg=args.cfg, denoise=1.0, filename_prefix=f"fig2_{label}",
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
