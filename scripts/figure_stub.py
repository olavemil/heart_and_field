#!/usr/bin/env python3
"""Stub figure pack from spike outputs (Phase 23 composite test).

Mattes a handful of spike figures to transparency with rembg, drops them
in game/assets/figures/, and writes a minimal figures.json so the
composite layer has something to show in-game before the real bake. Not
the real pipeline — the figure bake driver (step 3) replaces this.

    .venv/bin/python scripts/figure_stub.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "game"))

OUT = ROOT / "game" / "assets" / "figures"

# (source spike, output name, category, posture, appearance)
# Appearance is the coarse grid the descriptor maps onto.
STUBS = [
    # Player anchors — from-behind figures, one per gender bucket.
    ("figure_spike/interlocutor_tense_seed3000.png", "player_m.png",
     "player", "neutral",
     dict(gender="masculine", skin="light", hair_color="light",
          hair_length="short", age="adult")),
    ("figure_spike/manager_warm_seed3000.png", "player_f.png",
     "player", "neutral",
     dict(gender="feminine", skin="light", hair_color="dark",
          hair_length="long", age="adult")),
    # Frontal DE interlocutors.
    ("figure_spike3/front_warm_f_seed3000.png", "npc_warm_f.png",
     "interlocutor", "warm",
     dict(gender="feminine", skin="dark", hair_color="dark",
          hair_length="long", age="adult")),
    ("figure_spike3/front_tense_m_seed3000.png", "npc_tense_m.png",
     "interlocutor", "tense",
     dict(gender="masculine", skin="light", hair_color="light",
          hair_length="short", age="adult")),
    # Authority.
    ("figure_spike3/front_manager_m_seed3000.png", "manager_m.png",
     "authority", "neutral",
     dict(gender="masculine", skin="light", hair_color="dark",
          hair_length="short", age="older")),
]


def main() -> int:
    from PIL import Image
    from rembg import remove

    sys.path.insert(0, str(ROOT / "game"))
    from engine.figures import (  # noqa: E402
        FigureAppearance, FigureAsset, FigureCategory, FigureManifest,
        FigurePosture,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    mf = FigureManifest(assets_root=OUT)
    for src, name, cat, posture, app in STUBS:
        srcp = ROOT / src
        if not srcp.exists():
            print(f"skip (missing spike): {src}")
            continue
        cut = remove(Image.open(srcp).convert("RGBA"))
        cut.save(OUT / name)
        mf.add(FigureAsset(
            category=FigureCategory(cat),
            appearance=FigureAppearance(**app),
            posture=FigurePosture(posture),
            path=name,
        ))
        print(f"matted {src} -> figures/{name}  [{cat}/{posture}]")
    mf.save()
    print(f"\nwrote {OUT / 'figures.json'} with {len(mf.assets)} assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
