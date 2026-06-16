#!/usr/bin/env python3
"""Background quality spike — generate a handful of scenes for eyeballing.

Not the real pre-bake pipeline; a throwaway to judge ComfyUI output
quality before committing to the catalogue. Reuses the *runtime* prompt
machinery (LocationDescriptor.to_prompt_fragment + the producer's node
hints + prefix) and the producer's quality params (1280x720, 28 steps,
cfg 4.5) so what you see here is what the game would actually bake.

Requires ComfyUI on http://127.0.0.1:8000. Writes PNGs to
./prebake_spike/ (gitignored). Generates 2 seeds per scene to show the
"alternates" variability.

    .venv/bin/python scripts/prebake_spike.py
    .venv/bin/python scripts/prebake_spike.py --seeds 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "game"))

from engine.background_generator import (  # noqa: E402
    _BG_PROMPT_PREFIX,
    _NODE_PROMPT_HINTS,
)
from engine.background_pool import (  # noqa: E402
    Era,
    LocationDescriptor,
    LocationKind,
    MoodTone,
    Socioeconomic,
)
from engine.comfyui import ComfyUIClient  # noqa: E402

OUT = ROOT / "prebake_spike"

# Node-hint additions for nodes the runtime table doesn't cover yet.
EXTRA_HINTS = {
    "pitch": "football pitch from pitchside, empty stadium stands behind, daylight",
    "front_door": "house entrance hall just inside the front door, coats and shoes",
    "cantina": "school canteen / cafeteria, long tables and serving counter",
    "park": "public park, paths, trees, benches, open green space",
    "locker_room": "team locker room interior, benches and lockers, kit hanging",
}


def hint(node: str) -> str:
    return EXTRA_HINTS.get(node) or _NODE_PROMPT_HINTS.get(
        node, node.replace("_", " ")
    )


def build_prompt(desc: LocationDescriptor, node: str) -> str:
    return f"{_BG_PROMPT_PREFIX}{desc.to_prompt_fragment()}, {hint(node)}"


# (label, descriptor, node) — the six scenes requested for the spike.
SCENES = [
    (
        "locker_room",
        LocationDescriptor(
            kind=LocationKind.LOCKER_ROOM,
            socioeconomic=Socioeconomic.COMFORTABLE,
            mood=MoodTone.NEUTRAL,
            palette="painted concrete, wooden benches, club colours",
        ),
        "locker_room",
    ),
    (
        "pitch",
        LocationDescriptor(
            kind=LocationKind.STADIUM,
            mood=MoodTone.NEUTRAL,
            palette="green turf, white lines, overcast daylight",
        ),
        "pitch",
    ),
    (
        "house_entrance",
        LocationDescriptor(
            kind=LocationKind.SUBURBAN_HOUSE,
            socioeconomic=Socioeconomic.COMFORTABLE,
            mood=MoodTone.WARM,
            palette="warm oak floor, neutral walls",
        ),
        "front_door",
    ),
    (
        "bathroom",
        LocationDescriptor(
            kind=LocationKind.SUBURBAN_HOUSE,
            socioeconomic=Socioeconomic.COMFORTABLE,
            mood=MoodTone.NEUTRAL,
            palette="white tile, chrome fixtures",
        ),
        "bathroom",
    ),
    (
        "school_cantina",
        LocationDescriptor(
            kind=LocationKind.SCHOOL,
            socioeconomic=Socioeconomic.MODEST,
            mood=MoodTone.NEUTRAL,
            palette="linoleum floor, plastic chairs, strip lighting",
        ),
        "cantina",
    ),
    (
        "park",
        LocationDescriptor(
            kind=LocationKind.PARK,
            mood=MoodTone.WARM,
            palette="late afternoon light, autumn trees",
        ),
        "park",
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=2, help="alternates per scene")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--steps", type=int, default=28)
    ap.add_argument("--cfg", type=float, default=4.5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = ComfyUIClient()
    if not args.dry_run and not client.is_available():
        print("ComfyUI not reachable at", client.base_url, file=sys.stderr)
        return 1

    OUT.mkdir(exist_ok=True)
    for label, desc, node in SCENES:
        prompt = build_prompt(desc, node)
        print(f"\n=== {label} ===\n{prompt}")
        if args.dry_run:
            continue
        for s in range(args.seeds):
            seed = 1000 + s
            data = client.txt2img(
                prompt,
                seed=seed,
                width=args.width,
                height=args.height,
                steps=args.steps,
                cfg=args.cfg,
                denoise=1.0,
                filename_prefix=f"spike_{label}",
            )
            if data is None:
                print(f"  seed {seed}: FAILED")
                continue
            out = OUT / f"{label}_seed{seed}.png"
            out.write_bytes(data)
            print(f"  seed {seed}: {out.relative_to(ROOT)} ({len(data)//1024} KB)")
    print(f"\nDone. Inspect PNGs in {OUT.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
