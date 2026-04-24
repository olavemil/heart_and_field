#!/usr/bin/env python3
"""Batch-generate all game artwork via ComfyUI.

Run with:  python generate_art.py

Requires ComfyUI Desktop running on port 8000.
"""

import io
import sys
import time
from pathlib import Path

# Ensure game/ is on the path so engine imports work.
sys.path.insert(0, str(Path(__file__).parent / "game"))

from engine.comfyui import ComfyUIClient, face_prompt, background_prompt
from engine.visual import BACKGROUND_PROMPTS, FACE_WIDTH, FACE_HEIGHT
from PIL import Image

GENERATED = Path("game/generated")
FACES_DIR = GENERATED / "faces"
OVERLAYS_DIR = GENERATED / "overlays"
BACKGROUNDS_DIR = GENERATED / "backgrounds"
GUI_DIR = Path("game/gui")

# --- Characters to generate --------------------------------------------------

CHARACTERS = {
    "player": {
        "role": "forward",
        "age_group": "adult",
        "build": "athletic",
        "gender_presentation": "masculine",
    },
    "tm_jordan": {
        "role": "midfielder",
        "age_group": "adult",
        "build": "lean",
        "gender_presentation": "masculine",
    },
    "tm_sam": {
        "role": "defender",
        "age_group": "adult",
        "build": "stocky",
        "gender_presentation": "masculine",
    },
    "coach_williams": {
        "role": "manager",
        "age_group": "veteran",
        "build": "stocky",
        "gender_presentation": "masculine",
    },
}


def seed_from_id(cid: str) -> int:
    import hashlib
    h = hashlib.sha256(cid.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def generate_faces(client: ComfyUIClient) -> None:
    FACES_DIR.mkdir(parents=True, exist_ok=True)

    for cid, spec in CHARACTERS.items():
        out_path = FACES_DIR / f"{cid}.png"
        print(f"  Generating face: {cid}...", end=" ", flush=True)

        prompt = face_prompt(
            role=spec["role"],
            age_group=spec["age_group"],
            build=spec["build"],
            gender_presentation=spec["gender_presentation"],
        )
        seed = seed_from_id(cid)

        data = client.txt2img(
            prompt,
            seed=seed,
            width=512,
            height=512,
            steps=28,
            cfg=4.5,
            filename_prefix=f"fh_face_{cid}",
        )
        if data:
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            img = img.resize((FACE_WIDTH, FACE_HEIGHT), Image.LANCZOS)
            img.save(str(out_path), "PNG")
            print(f"OK ({out_path})")
        else:
            print("FAILED")

    # Clear overlay cache so new faces get fresh overlays
    if OVERLAYS_DIR.exists():
        for f in OVERLAYS_DIR.glob("*.png"):
            f.unlink()
        print("  Cleared overlay cache")


def generate_backgrounds(client: ComfyUIClient) -> None:
    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)

    for location, base_prompt in BACKGROUND_PROMPTS.items():
        out_path = BACKGROUNDS_DIR / f"{location}.png"
        print(f"  Generating background: {location}...", end=" ", flush=True)

        full_prompt = f"{base_prompt}, high quality, detailed environment, cinematic lighting"
        seed = hash(location) & 0xFFFFFFFF

        data = client.txt2img(
            full_prompt,
            seed=seed,
            width=1024,
            height=576,
            steps=28,
            cfg=4.5,
            filename_prefix=f"fh_bg_{location}",
        )
        if data:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img = img.resize((1280, 720), Image.LANCZOS)
            img.save(str(out_path), "PNG")
            print(f"OK ({out_path})")
        else:
            print("FAILED")


def generate_main_menu(client: ComfyUIClient) -> None:
    """Generate main menu and game menu background images."""
    GUI_DIR.mkdir(parents=True, exist_ok=True)

    menu_images = {
        "main_menu.png": (
            "dramatic sports stadium at dusk, empty pitch, floodlights casting "
            "long shadows, moody atmosphere, cinematic wide shot, dark teal and "
            "navy color palette, rain-slicked grass reflecting lights, "
            "high quality, film grain"
        ),
        "game_menu.png": (
            "football locker room interior, dimly lit, sports equipment on "
            "wooden benches, dramatic shadows, dark moody atmosphere, "
            "teal accent lighting, cinematic, high quality, film grain"
        ),
    }

    for filename, prompt in menu_images.items():
        out_path = GUI_DIR / filename
        print(f"  Generating {filename}...", end=" ", flush=True)

        data = client.txt2img(
            prompt,
            seed=42,
            width=1024,
            height=576,
            steps=28,
            cfg=4.5,
            filename_prefix=f"fh_gui_{filename.replace('.png', '')}",
        )
        if data:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img = img.resize((1280, 720), Image.LANCZOS)
            img.save(str(out_path), "PNG")
            print(f"OK ({out_path})")
        else:
            print("FAILED")


def main() -> None:
    client = ComfyUIClient()
    if not client.is_available():
        print("ERROR: ComfyUI is not available at", client.base_url)
        sys.exit(1)

    print(f"ComfyUI connected at {client.base_url}")
    models = client.list_models()
    if models:
        print(f"  Models: {models}")
    print()

    print("=== Character Faces ===")
    generate_faces(client)
    print()

    print("=== Backgrounds ===")
    generate_backgrounds(client)
    print()

    print("=== Menu Art ===")
    generate_main_menu(client)
    print()

    print("Done! All artwork saved to game/generated/ and game/gui/")


if __name__ == "__main__":
    main()
