#!/usr/bin/env python3
"""CLI for the two-step sprite pipeline.

Usage examples:

    # One character, explicit descriptor:
    python scripts/generate_sprites.py \\
        --gender masculine --age adult --skin medium --build athletic \\
        --hair short_brown

    # From one of the built-in presets (see PRESETS below):
    python scripts/generate_sprites.py --preset default_male_athlete

    # Batch generate the standard PoC roster in order:
    python scripts/generate_sprites.py --preset-batch poc_roster

Requires ComfyUI reachable at the URL baked into ``ComfyUIClient``
(defaults to ``http://127.0.0.1:8000``). The script does not fall back to
placeholder art — that is the runtime path's job, not the asset path's.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "game"))

from engine.comfyui import ComfyUIClient
from engine.sprite_generator import (
    DEFAULT_EXPRESSIONS,
    SpriteGenerationConfig,
    SpriteGenerator,
    SpriteGenerationError,
)
from engine.sprite_pool import (
    AgeBucket,
    Build,
    CharacterDescriptor,
    GenderPresentation,
    SkinTone,
    SpriteManifest,
)


DEFAULT_ASSETS_ROOT = Path("game/assets/characters")


# Build-order presets from the Phase 10 kickoff plan. Each value is a
# ``CharacterDescriptor``.
PRESETS: dict[str, CharacterDescriptor] = {
    "default_male_athlete": CharacterDescriptor(
        gender_presentation=GenderPresentation.MASCULINE,
        age_bucket=AgeBucket.ADULT,
        skin_tone=SkinTone.MEDIUM,
        build=Build.ATHLETIC,
        hair="short_brown",
        appearance_details=(
            "brown eyes, thick straight eyebrows, clean-shaven, "
            "straight nose, no freckles, no scars, hair parted left, "
            "short cropped sides"
        ),
    ),
    "default_female_athlete": CharacterDescriptor(
        gender_presentation=GenderPresentation.FEMININE,
        age_bucket=AgeBucket.ADULT,
        skin_tone=SkinTone.MEDIUM,
        build=Build.ATHLETIC,
        hair="ponytail_brown",
        appearance_details=(
            "hazel eyes, arched eyebrows, high cheekbones, "
            "hair pulled back in tight ponytail, small stud earrings, "
            "straight nose, light freckles across nose bridge"
        ),
    ),
    "young_man": CharacterDescriptor(
        gender_presentation=GenderPresentation.MASCULINE,
        age_bucket=AgeBucket.YOUNG,
        skin_tone=SkinTone.LIGHT,
        build=Build.LEAN,
        hair="short_blond",
        appearance_details=(
            "blue eyes, thin light eyebrows, soft jawline, "
            "wavy blond hair swept to right, no facial hair, "
            "light pink lips, rounded nose, no scars"
        ),
    ),
    "old_man": CharacterDescriptor(
        gender_presentation=GenderPresentation.MASCULINE,
        age_bucket=AgeBucket.VETERAN,
        skin_tone=SkinTone.MEDIUM,
        build=Build.STOCKY,
        hair="short_grey",
        facial_hair=True,
        appearance_details=(
            "grey-green eyes, bushy greying eyebrows, heavy brow ridge, "
            "close-cropped grey hair receding at temples, "
            "trimmed grey stubble, deep forehead lines, "
            "crow's feet, prominent square jaw"
        ),
    ),
    "young_woman": CharacterDescriptor(
        gender_presentation=GenderPresentation.FEMININE,
        age_bucket=AgeBucket.YOUNG,
        skin_tone=SkinTone.LIGHT,
        build=Build.LEAN,
        hair="long_black",
        appearance_details=(
            "dark brown almond-shaped eyes, long black lashes, "
            "thin arched eyebrows, straight black hair past shoulders, "
            "centre part, clear pale skin, small pointed chin"
        ),
    ),
    "old_woman": CharacterDescriptor(
        gender_presentation=GenderPresentation.FEMININE,
        age_bucket=AgeBucket.VETERAN,
        skin_tone=SkinTone.MEDIUM,
        build=Build.ATHLETIC,
        hair="short_grey",
        appearance_details=(
            "brown eyes, thin arched eyebrows, short silver-grey pixie cut, "
            "laugh lines around mouth, fine forehead wrinkles, "
            "strong defined jawline, no glasses"
        ),
    ),
}


PRESET_BATCHES: dict[str, list[str]] = {
    "poc_roster": [
        "default_male_athlete",
        "default_female_athlete",
        "young_man",
        "old_man",
        "young_woman",
        "old_woman",
    ],
}


def descriptor_from_args(args: argparse.Namespace) -> CharacterDescriptor:
    return CharacterDescriptor(
        gender_presentation=GenderPresentation(args.gender),
        age_bucket=AgeBucket(args.age),
        skin_tone=SkinTone(args.skin),
        build=Build(args.build),
        hair=args.hair,
        facial_hair=args.facial_hair,
        glasses=args.glasses,
        appearance_details=args.appearance_details,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--assets-root",
        type=Path,
        default=DEFAULT_ASSETS_ROOT,
        help=f"where sprites + manifest live (default: {DEFAULT_ASSETS_ROOT})",
    )
    p.add_argument("--preset", choices=sorted(PRESETS), help="named descriptor")
    p.add_argument(
        "--preset-batch",
        choices=sorted(PRESET_BATCHES),
        help="run a pre-defined batch in order",
    )
    p.add_argument("--reserved-for", help="character_id to reserve this sprite for")
    p.add_argument(
        "--expressions",
        nargs="+",
        default=list(DEFAULT_EXPRESSIONS),
        help="expressions to generate (default: the full standard set)",
    )
    p.add_argument("--seed", type=int, help="override the deterministic seed")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would happen without contacting ComfyUI",
    )

    # Descriptor axes (used when no --preset / --preset-batch is given).
    p.add_argument(
        "--gender",
        choices=[g.value for g in GenderPresentation],
        default=GenderPresentation.MASCULINE.value,
    )
    p.add_argument(
        "--age",
        choices=[a.value for a in AgeBucket],
        default=AgeBucket.ADULT.value,
    )
    p.add_argument(
        "--skin",
        choices=[s.value for s in SkinTone],
        default=SkinTone.MEDIUM.value,
    )
    p.add_argument(
        "--build",
        choices=[b.value for b in Build],
        default=Build.ATHLETIC.value,
    )
    p.add_argument("--hair", default="short_brown")
    p.add_argument("--facial-hair", action="store_true")
    p.add_argument("--glasses", action="store_true")
    p.add_argument(
        "--appearance-details",
        default="",
        help="free-text anchoring: eye colour, scars, hair texture, etc.",
    )

    return p


def resolve_descriptors(args: argparse.Namespace) -> list[CharacterDescriptor]:
    if args.preset_batch:
        return [PRESETS[name] for name in PRESET_BATCHES[args.preset_batch]]
    if args.preset:
        return [PRESETS[args.preset]]
    return [descriptor_from_args(args)]


def main() -> int:
    args = build_parser().parse_args()
    descriptors = resolve_descriptors(args)

    if args.dry_run:
        print(f"(dry run) assets_root={args.assets_root}")
        for d in descriptors:
            print(f"  would generate: {d.bucket_key()}  seed={args.seed}")
            print(f"    prompt fragment: {d.to_prompt_fragment()}")
        return 0

    client = ComfyUIClient()
    if not client.is_available():
        print(f"ERROR: ComfyUI not reachable at {client.base_url}", file=sys.stderr)
        return 2
    print(f"ComfyUI connected at {client.base_url}")

    manifest = SpriteManifest.load(args.assets_root)
    generator = SpriteGenerator(
        client=client,
        manifest=manifest,
        config=SpriteGenerationConfig(),
    )

    for descriptor in descriptors:
        # Reuse-before-generate: if a matching unclaimed entry already
        # exists, skip — the user can force regeneration by deleting it.
        existing = manifest.find_unclaimed(descriptor, character_id=args.reserved_for)
        if existing is not None and args.reserved_for is None:
            print(
                f"  skip: already have unclaimed sprite "
                f"{existing.entry_id!r} for {descriptor.bucket_key()!r}"
            )
            continue

        print(f"  generating: {descriptor.bucket_key()}")
        try:
            entry = generator.generate_set(
                descriptor,
                expressions=args.expressions,
                seed=args.seed,
                reserved_for=args.reserved_for,
            )
        except SpriteGenerationError as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            return 3

        print(
            f"  wrote {entry.entry_id} "
            f"({len(entry.variants)} variants → {args.assets_root / entry.neutral_path})"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
