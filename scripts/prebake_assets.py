#!/usr/bin/env python3
"""Manifest-driven background pre-bake (Phase 23D).

Enumerates every authored ``spec × node × alternate`` from
``game/content/scenes``, generates each shot offline with the locked
painterly recipe (ComfyUIImageProducer), and writes a read-only asset
pack + manifest the runtime loads in ``prebaked`` mode.

Idempotent: each shot is keyed by a stable ``(spec, node, alt)`` →
entry-id + path with a deterministic seed, so a rerun generates only
what's missing (newly-added nodes / raised alternate counts). Use
``--force`` to regenerate, ``--dry-run`` to preview the full plan.

    .venv/bin/python scripts/prebake_assets.py --dry-run
    .venv/bin/python scripts/prebake_assets.py --placeholder   # fast, no GPU
    .venv/bin/python scripts/prebake_assets.py                 # real bake
    .venv/bin/python scripts/prebake_assets.py --only suburban_house --force

One graph per spec (graph_id == spec_id) is the canonical pre-baked
instance; runtime cue→graph mapping for prebaked mode is step 5.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "game"))

from engine.background_generator import (  # noqa: E402
    ComfyUIImageProducer,
    PlaceholderImageProducer,
)

# Reuse the exact runtime prompt machinery (static method on the producer).
_build_prompt = ComfyUIImageProducer._build_prompt
from engine.background_pool import (  # noqa: E402
    BackgroundEntry,
    BackgroundManifest,
    Era,
    LocationDescriptor,
    MoodTone,
    SceneGraphSpec,
    Socioeconomic,
)
from engine.comfyui import ComfyUIClient  # noqa: E402
from engine.content_loader import load_scene_specs_from_path  # noqa: E402

DEFAULT_OUT = ROOT / "game" / "assets" / "backgrounds"
SCENES_DIR = ROOT / "game" / "content" / "scenes"

# Per-spec descriptor — palette/mood/socioeconomic that shape the prompt
# (kind comes from the spec). Validated against the spike; the negative
# prompt + node hints carry the per-room specifics.
SPEC_DESCRIPTORS: dict[str, dict] = {
    "suburban_house": dict(
        socioeconomic=Socioeconomic.COMFORTABLE, mood=MoodTone.WARM,
        palette="warm oak floors, neutral walls, lived-in",
    ),
    "apartment": dict(
        socioeconomic=Socioeconomic.MODEST, mood=MoodTone.NEUTRAL,
        palette="compact modern flat, white walls, soft daylight",
    ),
    "team_hq": dict(
        socioeconomic=Socioeconomic.COMFORTABLE, mood=MoodTone.NEUTRAL,
        palette="painted concrete, club colours, functional",
    ),
    "training_ground": dict(
        mood=MoodTone.NEUTRAL,
        palette="green training pitch, overcast daylight",
    ),
    "pitch": dict(
        mood=MoodTone.NEUTRAL,
        palette="green turf, white lines, stadium, overcast daylight",
    ),
    "cafe": dict(
        socioeconomic=Socioeconomic.COMFORTABLE, mood=MoodTone.WARM,
        palette="warm wood, soft lamplight, cosy",
    ),
    "bar": dict(
        socioeconomic=Socioeconomic.MODEST, mood=MoodTone.WARM,
        palette="dark wood, brass, dim evening light, pub",
    ),
    "media": dict(
        socioeconomic=Socioeconomic.COMFORTABLE, mood=MoodTone.NEUTRAL,
        palette="branded backdrop, bright even lighting, corporate",
    ),
    "transit": dict(
        socioeconomic=Socioeconomic.COMFORTABLE, mood=MoodTone.NEUTRAL,
        palette="coach seats, motorway light through windows",
    ),
    "school": dict(
        socioeconomic=Socioeconomic.MODEST, mood=MoodTone.NEUTRAL,
        palette="institutional, linoleum, strip lighting",
    ),
}


def descriptor_for(spec: SceneGraphSpec) -> LocationDescriptor:
    kw = dict(SPEC_DESCRIPTORS.get(spec.spec_id, {}))
    return LocationDescriptor(kind=spec.kind, era=Era.MODERN, **kw)


def seed_for(spec_id: str, node: str, alt: int) -> int:
    """Deterministic, process-independent seed per shot."""
    h = hashlib.sha256(f"{spec_id}/{node}/{alt}".encode()).hexdigest()
    return int(h[:8], 16)


def entry_id_for(spec_id: str, node: str, alt: int) -> str:
    return f"{spec_id}__{node}__alt{alt}"


def rel_path_for(desc: LocationDescriptor, spec_id: str, node: str, alt: int) -> str:
    return f"{desc.bucket_key()}/{spec_id}/{node}__alt{alt}.png"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--only", help="restrict to one spec_id")
    ap.add_argument("--force", action="store_true", help="regenerate existing shots")
    ap.add_argument("--placeholder", action="store_true", help="no GPU; solid PNGs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    specs = load_scene_specs_from_path(SCENES_DIR)
    if args.only:
        specs = [s for s in specs if s.spec_id == args.only]
        if not specs:
            print(f"no spec named {args.only!r}", file=sys.stderr)
            return 1

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = BackgroundManifest.load(args.out)

    producer = None
    if not args.dry_run:
        if args.placeholder:
            producer = PlaceholderImageProducer()
        else:
            client = ComfyUIClient()
            if not client.is_available():
                print("ComfyUI not reachable at", client.base_url, file=sys.stderr)
                return 1
            producer = ComfyUIImageProducer(client=client)

    planned = generated = skipped = 0
    for spec in sorted(specs, key=lambda s: s.spec_id):
        desc = descriptor_for(spec)
        if manifest.get_graph(spec.spec_id) is None:
            manifest.create_graph(spec.spec_id, desc, graph_id=spec.spec_id)
        for node in spec.nodes:
            for alt in range(spec.alternate_count(node)):
                planned += 1
                eid = entry_id_for(spec.spec_id, node, alt)
                rel = rel_path_for(desc, spec.spec_id, node, alt)
                abs_path = manifest.resolve(rel)
                exists = abs_path.exists()
                attached = eid in manifest.get_graph(spec.spec_id).node_alternates.get(node, [])

                if exists and attached and not args.force:
                    skipped += 1
                    continue

                prompt = _build_prompt(desc, node)
                if args.dry_run:
                    print(f"GEN  {spec.spec_id}/{node} alt{alt}  seed={seed_for(spec.spec_id, node, alt)}")
                    print(f"       {prompt}")
                    generated += 1
                    continue

                if not exists or args.force:
                    producer.produce(
                        descriptor=desc, spec=spec, node_name=node,
                        seed=seed_for(spec.spec_id, node, alt),
                        anchor_path=None, out_path=abs_path, variant_index=0,
                    )
                if not abs_path.exists():
                    print(f"FAILED {spec.spec_id}/{node} alt{alt}", file=sys.stderr)
                    continue
                if not attached:
                    manifest.attach_alternate(
                        spec.spec_id, node,
                        BackgroundEntry(
                            entry_id=eid, descriptor=desc, spec_id=spec.spec_id,
                            node_name=node, image_paths=[rel],
                            seed=seed_for(spec.spec_id, node, alt),
                        ),
                    )
                generated += 1
                print(f"{spec.spec_id}/{node} alt{alt}: {rel}")

    if not args.dry_run:
        manifest.save()
    verb = "would generate" if args.dry_run else "generated"
    print(f"\nplan: {planned} shots | {verb}: {generated} | skipped(existing): {skipped}")
    if not args.dry_run:
        print(f"pack: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
