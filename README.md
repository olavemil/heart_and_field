# Field & Heart

Sports drama simulation. A pure-Python engine drives all gameplay; Ren'Py serves as the display shell.

## Requirements

- **Python 3.11+** (engine and tests)
- **Ren'Py 8.5.2 SDK** (bundled at `renpy-8.5.2-sdk/`)
- **NumPy** and **Pillow** (installed into both the dev venv and the Ren'Py SDK)
- **ComfyUI** (optional) — enables AI-generated backgrounds and character sprites

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # macOS / Linux

# Install dependencies
pip install -e ".[dev]"
pip install Pillow
```

### Ren'Py SDK dependencies

Ren'Py ships its own Python 3.12. NumPy and Pillow must also be installed into its site-packages:

```bash
pip install numpy Pillow \
  --target renpy-8.5.2-sdk/lib/python3.12/site-packages \
  --python-version 3.12 \
  --only-binary=:all: \
  --platform macosx_11_0_arm64
```

Adjust `--platform` for your OS (e.g. `manylinux2014_x86_64` on Linux).

## Running the game

### macOS

```bash
renpy-8.5.2-sdk/lib/py3-mac-universal/renpy . run
```

### Linux / Windows

```bash
renpy-8.5.2-sdk/renpy.sh . run      # Linux
renpy-8.5.2-sdk/renpy.exe . run     # Windows
```

The `.` argument tells Ren'Py to use the current directory as the project root (where `game/` lives).

## Running tests

```bash
source .venv/bin/activate
pytest
```

All engine tests live in `tests/`. The test suite runs against the pure-Python engine without Ren'Py.

## Optional: ComfyUI (AI image generation)

If [ComfyUI](https://github.com/comfyanonymous/ComfyUI) is running locally, the game generates backgrounds and character sprites via Stable Diffusion. Without it, placeholder images are used automatically.

The default ComfyUI endpoint is `http://127.0.0.1:8000`. The engine supports two pipelines:

- **SD3.5** (default) — requires `sd3.5_medium.safetensors`, `clip_l.safetensors`, `clip_g.safetensors`
- **Flux 2** — requires `flux2_dev_fp8mixed.safetensors`, `mistral_3_small_flux2_bf16.safetensors`, `full_encoder_small_decoder.safetensors`, `Flux_2-Turbo-LoRA_comfyui.safetensors`

## Project structure

```
game/
  engine/      # pure-Python simulation (all logic)
  content/     # authored data (events, templates, arcs)
  scripts/     # Ren'Py .rpy labels (display + flow only)
  assets/      # images, audio, fonts
tests/         # pytest suite
notebooks/     # prototyping and distribution validation
```

The engine is **never** imported by Ren'Py internals — Ren'Py labels call engine methods and display the results. No simulation logic lives in `.rpy` files.
