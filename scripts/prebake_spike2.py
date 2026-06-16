#!/usr/bin/env python3
"""Background quality spike v2 — painterly-style tuning pass.

Feedback from v1: output read too pixelated / DOS-era and too literal,
which also exposed incoherent geometry (Escher bathroom). Fixes tried
here, all art-direction levers (no engine API change yet):

  - Strong painterly/impressionistic style cue; drop "detailed" / sharp.
  - Negative prompt against pixel-art / CGI / sharp / duplicated fixtures.
  - More sampling steps (44) and a smoother sampler (dpmpp_2m / karras).
  - Per-scene colour pinning (e.g. "Green" team locker room → green
    branding throughout).

Builds the SD3 workflow directly and submits via the client so we can
set negative prompt + sampler without touching the engine. Once settings
are dialled in, fold them into ComfyUIImageProducer.

    .venv/bin/python scripts/prebake_spike2.py            # all scenes, 2 seeds
    .venv/bin/python scripts/prebake_spike2.py --only locker_room --seeds 4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "game"))

from engine.comfyui import ComfyUIClient, _sd3_txt2img_workflow  # noqa: E402

OUT = ROOT / "prebake_spike2"

# Painterly style — loose, atmospheric, evocative over literal/sharp.
STYLE = (
    "loose painterly digital painting, impressionistic, soft visible "
    "brushwork, atmospheric, muted natural palette, soft focus, gentle "
    "gradients, evocative mood, visual-novel background art, no people, "
    "no text"
)
NEGATIVE = (
    "pixel art, dithering, 8-bit, retro game, low resolution, sharp hard "
    "edges, crisp linework, 3d render, cgi, plastic, photorealistic, "
    "text, watermark, logo, people, person, faces, distorted geometry, "
    "warped perspective, duplicated fixtures, extra sinks, extra doors, "
    "floating objects, clutter"
)

# (label, subject) — subject is the concrete scene; STYLE wraps it.
SCENES = {
    "locker_room": (
        "interior of a sports team locker room for the GREEN team, "
        "rows of green lockers, green bench seating, green and white team "
        "colours throughout, green club branding and trim, kit bags, "
        "soft indoor light"
    ),
    "pitch": (
        "standing pitchside in a football stadium on match day, packed "
        "crowd in the stands, a sea of supporters, banners and flags, "
        "floodlights, electric atmosphere, green pitch in the foreground, "
        "hazy depth, blotchy painterly crowd"
    ),
    "house_entrance": (
        "entrance hall just inside the front door of a comfortable "
        "suburban home, coat hooks, a runner rug, warm afternoon light "
        "from the doorway, glimpse of the living room beyond"
    ),
    "bathroom": (
        "a single small domestic bathroom, one sink with a mirror, a "
        "bathtub, white and pale-blue tiles, frosted window with soft "
        "daylight, calm and simple, one coherent room"
    ),
    "school_cantina": (
        "a school cafeteria canteen, long tables with chairs, a serving "
        "counter at the back, large windows, bright airy daytime light"
    ),
    "park": (
        "a public park in late afternoon autumn light, winding path, "
        "golden trees, scattered leaves, a few benches, soft hazy depth"
    ),
}


def workflow_for(subject: str, *, seed: int, w: int, h: int, steps: int, cfg: float):
    prompt = f"{subject}, {STYLE}"
    # Keep euler/sgm_uniform — SD3.5-medium NaNs to black on off-combo
    # samplers (dpmpp_2m/karras produced black + timeouts in testing).
    wf = _sd3_txt2img_workflow(
        prompt,
        negative_prompt=NEGATIVE,
        seed=seed,
        width=w,
        height=h,
        steps=steps,
        cfg=cfg,
        denoise=1.0,
        filename_prefix="spike2",
    )
    return wf, prompt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="generate just this scene label")
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--steps", type=int, default=32)
    ap.add_argument("--cfg", type=float, default=4.5)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = ComfyUIClient(timeout=args.timeout)
    if not args.dry_run and not client.is_available():
        print("ComfyUI not reachable at", client.base_url, file=sys.stderr)
        return 1

    scenes = (
        {args.only: SCENES[args.only]} if args.only else SCENES
    )
    OUT.mkdir(exist_ok=True)
    for label, subject in scenes.items():
        for s in range(args.seeds):
            seed = 2000 + s
            wf, prompt = workflow_for(
                subject, seed=seed, w=args.width, h=args.height,
                steps=args.steps, cfg=args.cfg,
            )
            if args.dry_run:
                print(f"\n=== {label} seed {seed} ===\n{prompt}")
                break
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
