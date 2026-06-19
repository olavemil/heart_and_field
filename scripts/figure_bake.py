#!/usr/bin/env python3
"""Figure bake driver (Phase 23 figure layer, step 3).

Enumerates the figure catalogue (category × appearance × posture),
generates each with the locked recipe — frontal Disco-Elysium sketch
(gaze toward the lower-left MC) for NPCs, from-behind for the player and
motion/anonymous figures — mattes to transparency with rembg, and writes
game/assets/figures/ + figures.json.

Idempotent like prebake_assets.py: stable path + deterministic seed per
asset; skips what's on disk. Both genders are always baked per category
(selection can't invent a gender that wasn't baked).

    .venv/bin/python scripts/figure_bake.py --dry-run
    .venv/bin/python scripts/figure_bake.py --only interlocutor
    .venv/bin/python scripts/figure_bake.py --placeholder   # no GPU
    .venv/bin/python scripts/figure_bake.py                 # full bake
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "game"))

from engine.comfyui import ComfyUIClient, _sd3_txt2img_workflow  # noqa: E402
from engine.figures import (  # noqa: E402
    FigureAppearance, FigureAsset, FigureCategory, FigureContext,
    FigureManifest, FigurePosture,
)

OUT = ROOT / "game" / "assets" / "figures"

# --- Locked recipes (from the spikes) --------------------------------------

# Forward-facing toward the camera, eyes glancing toward the foreground
# MC (lower-left) — NOT a head turned to the side, which reads as profile.
GAZE_NPC = "facing the viewer, body toward the camera, glancing toward the lower left"
FRONTAL_STYLE = (
    "Disco Elysium style painted character study, loose oil and ink "
    "sketch, thick visible brushstrokes, gestural sketchy linework, "
    "impressionistic abstracted face with soft indistinct blurred "
    "features, unfinished painterly sketch, muted desaturated palette, "
    "moody, full-length figure from head to knees, standing, wide "
    "full-body framing, plain muted background"
)
FRONTAL_NEG = (
    # Anti-headshot (keep the torso in frame, consistent with composites)
    "close-up, headshot, portrait crop, "
    # Anti-profile / wrong-facing (we want forward + left gaze)
    "profile, side view, "
    # Style guards
    "photorealistic, photograph, smooth skin, sharp focus, detailed eyes, "
    "detailed rendered face, glamour, beauty shot, anime, cartoon, clean "
    "lines, 3d render, cgi, pixel art, text, watermark, deformed, extra "
    "limbs, extra fingers"
)
BEHIND_STYLE = (
    "very loose impressionistic oil painting, abstract gestural brushwork, "
    "palette-knife strokes, simplified blocky forms, soft blurred edges, "
    "the figure suggested rather than detailed, seen from behind, back to "
    "camera, head turned away, anonymous, muted palette, plain neutral "
    "background, alla prima, full body"
)
BEHIND_NEG = (
    "ball, football, sports ball, holding a ball, "
    "face, facial features, eyes, mouth, portrait, looking at viewer, "
    "front view, facing camera, detailed face, identifiable person, sharp "
    "focus, fine detail, photorealistic, photograph, 3d render, cgi, "
    "pixel art, text, watermark, deformed, extra limbs"
)

# --- Appearance vocabulary --------------------------------------------------

GENDERS = ("masculine", "feminine")
SKINS = ("light", "dark")
HAIR_COLORS = ("dark", "light", "red")
HAIR_LENGTHS = ("short", "long")


def _gender_word(g: str) -> str:
    return "woman" if g == "feminine" else "man"


def _skin_word(s: str) -> str:
    return "dark-skinned" if s == "dark" else "light-skinned"


def _hair_word(color: str, length: str) -> str:
    c = {"dark": "dark", "light": "blonde", "red": "red"}[color]
    return f"{length} {c} hair"


def _full_grid() -> list[FigureAppearance]:
    out = []
    for g in GENDERS:
        for s in SKINS:
            for c in HAIR_COLORS:
                for ln in HAIR_LENGTHS:
                    out.append(FigureAppearance(g, s, c, ln, "adult"))
    return out  # 24


def _mid_grid() -> list[FigureAppearance]:
    return [FigureAppearance(g, s, c, "short", "adult")
            for g in GENDERS for s in SKINS for c in ("dark", "light")]  # 8


def _coarse(age: str = "adult") -> list[FigureAppearance]:
    return [FigureAppearance(g, s, "dark", "short", age)
            for g in GENDERS for s in SKINS]  # 4


# --- Posture phrasing -------------------------------------------------------

_INTERLOCUTOR = {
    # "Welcoming" open-armed gesture (vs tense arms-crossed) — also forces
    # the torso into frame, fixing the head-only crops the smile produced.
    FigurePosture.WARM: "welcoming open-armed posture, standing, arms "
                        "slightly spread, relaxed and inviting",
    FigurePosture.NEUTRAL: "neutral attentive posture, standing, hands at "
                           "their sides",
    FigurePosture.TENSE: "arms crossed, guarded tense posture, standing",
}
_AUTHORITY = {
    FigurePosture.COMFORTING: "arms open, encouraging and comforting posture",
    FigurePosture.SCEPTICAL: "arms folded, sceptical questioning posture",
    FigurePosture.ANGRY: "pointing, stern and angry posture",
    FigurePosture.NEUTRAL: "standing composed",
}


@dataclass
class Spec:
    asset: FigureAsset
    prompt: str
    frontal: bool


def _spec(cat, app: FigureAppearance, posture, frontal, prompt,
          context=FigureContext.DEFAULT) -> Spec:
    # Default-context paths stay as before (don't invalidate the existing
    # bake); other contexts get a prefix.
    ctx = "" if context is FigureContext.DEFAULT else f"{context.value}_"
    name = (
        f"{cat.value}/{ctx}{app.gender}_{app.skin}_{app.hair_color}_"
        f"{app.hair_length}_{app.age}_{posture.value}.png"
    )
    return Spec(FigureAsset(cat, app, posture, name, context), prompt, frontal)


def enumerate_catalogue() -> list[Spec]:
    specs: list[Spec] = []

    # Interlocutors — the reuse pool. Full grid for warm/tense, mid for neutral.
    for app in _full_grid():
        for posture in (FigurePosture.WARM, FigurePosture.TENSE):
            subj = (
                f"a {_skin_word(app.skin)} {_gender_word(app.gender)} with "
                f"{_hair_word(app.hair_color, app.hair_length)}, "
                f"{_INTERLOCUTOR[posture]}, casual clothes, {GAZE_NPC}"
            )
            specs.append(_spec(FigureCategory.INTERLOCUTOR, app, posture, True,
                               f"{subj}, {FRONTAL_STYLE}"))
    for app in _mid_grid():
        subj = (f"a {_skin_word(app.skin)} {_gender_word(app.gender)} with "
                f"{_hair_word(app.hair_color, app.hair_length)}, "
                f"{_INTERLOCUTOR[FigurePosture.NEUTRAL]}, casual clothes, {GAZE_NPC}")
        specs.append(_spec(FigureCategory.INTERLOCUTOR, app, FigurePosture.NEUTRAL,
                           True, f"{subj}, {FRONTAL_STYLE}"))

    # Locker-room / shower interlocutors — context-appropriate dress so
    # conversations in those scenes have a real frontal partner (not the
    # casual-clothes default, and not a from-behind anonymous figure).
    for ctx, dress, postures in (
        (FigureContext.SHOWER, "undressed, steamy, wet, vibrant, communal shower "
         "room, approachable",
         (FigurePosture.WARM, FigurePosture.NEUTRAL)),
        (FigureContext.SHOWER, "with a towel, steam, communal shower "
         "room, colorful, skeptical",
         (FigurePosture.TENSE, FigurePosture.TENSE)),
        (FigureContext.LOCKER, "wearing locker-room kit, partially dressed,"
         "standing by the lockers",
         (FigurePosture.WARM, FigurePosture.NEUTRAL, FigurePosture.TENSE)),
    ):
        for app in _coarse("adult"):
            for posture in postures:
                pose = _INTERLOCUTOR[posture].split(",")[0]
                subj = (f"a {_skin_word(app.skin)} {_gender_word(app.gender)} "
                        f"{dress}, {pose}, {GAZE_NPC}")
                specs.append(_spec(FigureCategory.INTERLOCUTOR, app, posture,
                                True, f"{subj}, {FRONTAL_STYLE}", ctx))

    # Authority — both genders × both ages × four postures.
    for age in ("adult", "older"):
        for app in _coarse(age):
            for posture, phrase in _AUTHORITY.items():
                art = "an older" if age == "older" else "a"
                subj = (f"{art} {_skin_word(app.skin)} "
                        f"{_gender_word(app.gender)} football coach in a "
                        f"tracksuit, {phrase}, {GAZE_NPC}")
                specs.append(_spec(FigureCategory.AUTHORITY, app, posture, True,
                                   f"{subj}, {FRONTAL_STYLE}"))

    # Service / medical / office — coarse, neutral.
    for cat, dress in (
        (FigureCategory.SERVICE, "cafe waiter in an apron"),
        (FigureCategory.MEDICAL, "doctor in a white coat with a stethoscope"),
        (FigureCategory.OFFICE, "office worker in smart clothes"),
    ):
        for app in _coarse():
            subj = (f"a {_skin_word(app.skin)} {_gender_word(app.gender)} "
                    f"{dress}, standing, {GAZE_NPC}")
            specs.append(_spec(cat, app, FigurePosture.NEUTRAL, True,
                               f"{subj}, {FRONTAL_STYLE}"))

    # Player — from-behind anchor, both genders, hair visible.
    for app in [FigureAppearance(g, s, c, ln, "adult")
                for g in GENDERS for s in SKINS
                for c in ("dark", "light") for ln in HAIR_LENGTHS]:  # 16
        subj = (f"a {_gender_word(app.gender)} with "
                f"{_hair_word(app.hair_color, app.hair_length)}, casual "
                f"clothes, seen from behind, angled to the right")
        specs.append(_spec(FigureCategory.PLAYER, app, FigurePosture.NEUTRAL,
                           False, f"{subj}, {BEHIND_STYLE}"))

    # Motion (match) — one running pose per sport × gender, from behind.
    for sport in ("soccer", "rugby", "basketball"):
        for g in GENDERS:
            app = FigureAppearance(g, "light", "dark", "short", "adult")
            # No ball — it rendered in odd places (behind the back). The
            # negative (BEHIND_NEG) also forbids it.
            subj = (f"a {_gender_word(g)} {sport} player running, dynamic "
                    f"athletic action, sports kit, seen from behind, "
                    f"running away")
            # Encode sport in the path so the keys don't collide.
            sp = _spec(FigureCategory.MOTION, app, FigurePosture.ACTION, False,
                       f"{subj}, {BEHIND_STYLE}")
            sp.asset = FigureAsset(
                FigureCategory.MOTION, app, FigurePosture.ACTION,
                f"motion/{sport}_{g}.png",
            )
            specs.append(sp)

    # Anonymous (locker/shower), from behind.
    for g in GENDERS:
        for pose, phrase in (("locker", "standing at a locker"),
                             ("shower", "in a communal shower, steamy")):
            app = FigureAppearance(g, "light", "dark", "short", "adult")
            subj = (f"an anonymous {_gender_word(g)} figure {phrase}, locker "
                    f"room, seen from behind")
            sp = _spec(FigureCategory.ANONYMOUS, app, FigurePosture.PERIPHERAL,
                       False, f"{subj}, {BEHIND_STYLE}")
            sp.asset = FigureAsset(
                FigureCategory.ANONYMOUS, app, FigurePosture.PERIPHERAL,
                f"anonymous/{g}_{pose}.png",
            )
            specs.append(sp)

    return specs


def _seed(path: str) -> int:
    return int(hashlib.sha256(path.encode()).hexdigest()[:8], 16)


def _placeholder(out: Path, frontal: bool) -> None:
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (832, 1216), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = (90, 110, 140, 200) if frontal else (40, 40, 50, 220)
    d.ellipse([216, 80, 616, 1180], fill=col)  # crude figure blob
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="restrict to one category")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--placeholder", action="store_true", help="no GPU")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--steps", type=int, default=34)
    ap.add_argument("--cfg", type=float, default=4.5)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument(
        "--prune", action="store_true",
        help="drop manifest entries whose file is gone (after moving "
             "rejects out), then a plain re-run refills them",
    )
    args = ap.parse_args()

    if args.prune:
        if not (OUT / "figures.json").exists():
            print("no figures.json to prune")
            return 0
        mf = FigureManifest.load(OUT)
        before = len(mf.assets)
        if before == 0:
            print("manifest empty; nothing to prune (not overwriting)")
            return 0
        mf.assets = [a for a in mf.assets if (OUT / a.path).exists()]
        removed = before - len(mf.assets)
        if removed:
            mf.save()  # only rewrite when something actually changed
        print(f"pruned {removed} missing; {len(mf.assets)} remain")
        return 0

    specs = enumerate_catalogue()
    if args.only:
        specs = [s for s in specs if s.asset.category.value == args.only]
        if not specs:
            print(f"no category {args.only!r}", file=sys.stderr)
            return 1

    client = None
    remove = None
    if not args.dry_run and not args.placeholder:
        client = ComfyUIClient(timeout=args.timeout)
        if not client.is_available():
            print("ComfyUI not reachable at", client.base_url, file=sys.stderr)
            return 1
        from rembg import remove as _remove
        remove = _remove

    OUT.mkdir(parents=True, exist_ok=True)
    mf = FigureManifest.load(OUT)
    have = {a.path for a in mf.assets}

    planned = generated = skipped = 0
    for sp in specs:
        planned += 1
        rel = sp.asset.path
        abs_path = OUT / rel
        if abs_path.exists() and rel in have and not args.force:
            skipped += 1
            continue
        if args.dry_run:
            print(f"GEN {rel}\n    {sp.prompt[:150]}")
            generated += 1
            continue
        if args.placeholder:
            _placeholder(abs_path, sp.frontal)
        else:
            style_neg = FRONTAL_NEG if sp.frontal else BEHIND_NEG
            wf = _sd3_txt2img_workflow(
                sp.prompt, negative_prompt=style_neg, seed=_seed(rel),
                width=832, height=1216, steps=args.steps, cfg=args.cfg,
                denoise=1.0, filename_prefix="fig_bake",
            )
            data = client._submit_and_wait(wf)
            if data is None:
                print(f"FAILED {rel}", file=sys.stderr)
                continue
            from io import BytesIO
            from PIL import Image
            cut = remove(Image.open(BytesIO(data)).convert("RGBA"))
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            cut.save(abs_path, "PNG")
        if rel not in have:
            mf.add(sp.asset)
            have.add(rel)
        generated += 1
        print(f"{rel}")
        # Persist periodically so a long bake shows up in-game as it runs
        # (and an interrupted run keeps its progress in the manifest).
        if not args.placeholder and generated % 8 == 0:
            mf.save()

    if not args.dry_run:
        mf.save()
    verb = "would generate" if args.dry_run else "generated"
    print(f"\nplan: {planned} | {verb}: {generated} | skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
