#!/usr/bin/env python3
"""Generate a pool of stock reference faces for img2img character generation.

Usage:

    python scripts/generate_stock_faces.py                # full default pool
    python scripts/generate_stock_faces.py --count 2      # 2 per bucket
    python scripts/generate_stock_faces.py --dry-run      # preview what would generate

Requires ComfyUI reachable (defaults to http://127.0.0.1:8000).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "game"))

from engine.comfyui import ComfyUIClient
from engine.stock_faces import StockFace, StockFacePool

DEFAULT_OUTPUT = Path("game/assets/stock_faces")

# Buckets: (gender_presentation, age_bucket, prompt_fragment)
STOCK_BUCKETS: list[tuple[str, str, str]] = [
    (
        "masculine",
        "young",
        "young man in his early twenties, masculine presenting, athletic build, "
        "short brown hair, clean-shaven",
    ),
    (
        "masculine",
        "adult",
        "man in his late twenties, masculine presenting, athletic build, "
        "short dark hair, light stubble",
    ),
    (
        "masculine",
        "veteran",
        "man in his mid-thirties, masculine presenting, stocky muscular build, "
        "short grey-brown hair, trimmed facial hair, weathered face",
    ),
    (
        "feminine",
        "young",
        "young woman in her early twenties, feminine presenting, lean build, "
        "long dark hair, clear skin",
    ),
    (
        "feminine",
        "adult",
        "woman in her late twenties, feminine presenting, athletic build, "
        "ponytail brown hair, high cheekbones",
    ),
    (
        "feminine",
        "veteran",
        "woman in her mid-thirties, feminine presenting, athletic build, "
        "short hair, fine lines around eyes, strong jawline",
    ),
    (
        "androgynous",
        "young",
        "young person in their early twenties, androgynous presenting, lean build, "
        "medium-length wavy hair, soft features",
    ),
    (
        "androgynous",
        "adult",
        "person in their late twenties, androgynous presenting, athletic build, "
        "short tousled hair, angular features",
    ),
]

PROMPT_PREFIX = (
    "professional close-up portrait painting, full head and shoulders only, "
    "painterly style, "
)

PROMPT_SUFFIX = (
    ", plain neutral grey background, soft studio lighting, "
    "sharp focus on face, natural skin texture, shot on 85mm lens, "
    "wearing plain dark crew-neck shirt, neutral relaxed expression, "
    "mouth closed, brows relaxed, looking at camera, "
    "entire head including hair"
)

NEGATIVE_PROMPT = (
    "distorted face, artifacting, poorly done, extra limbs, blurry, "
    "low quality, watermark, text, logo, badge, emblem, crest, "
    "uniform details, nsfw, bored, unreadable"
)


def generate_stock_faces(
    client: ComfyUIClient,
    output_dir: Path,
    *,
    count_per_bucket: int = 3,
    seed_base: int = 0xFACE,
    dry_run: bool = False,
) -> StockFacePool:
    """Generate stock face images and write the manifest."""
    pool = StockFacePool.load(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    for bucket_idx, (gender, age, desc_fragment) in enumerate(STOCK_BUCKETS):
        for variant in range(count_per_bucket):
            filename = f"{gender}_{age}_{variant:03d}.png"
            out_path = output_dir / filename

            # Skip if already exists in pool and on disk.
            existing = [f for f in pool.faces if f.filename == filename]
            if existing and out_path.exists():
                print(f"  skip {filename} (exists)")
                continue

            seed = seed_base + bucket_idx * 100 + variant
            prompt = PROMPT_PREFIX + desc_fragment + PROMPT_SUFFIX

            if dry_run:
                print(f"  [dry-run] would generate {filename} (seed={seed})")
                continue

            print(f"  generating {filename} (seed={seed}) ... ", end="", flush=True)
            data = client.txt2img(
                prompt,
                seed=seed,
                width=512,
                height=512,
                steps=28,
                cfg=4.5,
                filename_prefix=f"fh_stock_{gender}_{age}_{variant}",
            )
            if data is None:
                print("FAILED (ComfyUI returned None)")
                continue

            # Save to disk.
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(data)).convert("RGBA")
            img.save(str(out_path), "PNG")

            face = StockFace(
                filename=filename,
                gender_presentation=gender,
                age_bucket=age,
            )
            if not existing:
                pool.add(face)
            generated += 1
            print("OK")

    if not dry_run:
        pool.save()
        print(f"\nDone. Generated {generated} new faces, "
              f"{len(pool.faces)} total in manifest.")
    else:
        print(f"\n[dry-run] Would generate up to "
              f"{len(STOCK_BUCKETS) * count_per_bucket} faces.")

    return pool


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"output directory (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="faces per bucket (default: 3)",
    )
    parser.add_argument(
        "--seed-base",
        type=int,
        default=0xFACE,
        help="base seed for generation (default: 0xFACE)",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
        help="ComfyUI base URL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="preview without generating",
    )
    args = parser.parse_args()

    client = ComfyUIClient(base_url=args.url)
    if not args.dry_run and not client.is_available():
        print("ERROR: ComfyUI not reachable at", args.url)
        sys.exit(1)

    print(f"Stock face pool: {args.output}")
    print(f"Buckets: {len(STOCK_BUCKETS)}, count per bucket: {args.count}")
    print()

    generate_stock_faces(
        client,
        args.output,
        count_per_bucket=args.count,
        seed_base=args.seed_base,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
