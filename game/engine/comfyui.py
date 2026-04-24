"""ComfyUI API client — image generation via Flux 2 or SD3.5 workflows.

Provides txt2img and img2img generation through ComfyUI's REST API.
Supports two pipelines:
- **flux2**: UNETLoader → CLIPLoader (Mistral) → CLIPTextEncode → KSampler
- **sd3**: CheckpointLoaderSimple → CLIPTextEncode → KSampler (with negative)

Like ``llm.py``, this client is **optional**: if ComfyUI is unavailable,
``visual.py`` falls back to its PIL placeholder generator silently.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

log = logging.getLogger(__name__)

# --- Configuration -----------------------------------------------------------

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 120  # seconds — image gen can be slow
POLL_INTERVAL = 1.0  # seconds between status checks
MAX_CONSECUTIVE_ERRORS = 3

# Default models discovered from LM Studio instance
DEFAULT_UNET = "flux2_dev_fp8mixed.safetensors"
DEFAULT_WEIGHT_DTYPE = "fp8_e4m3fn_fast"
DEFAULT_CLIP = "mistral_3_small_flux2_bf16.safetensors"
DEFAULT_VAE = "full_encoder_small_decoder.safetensors"
DEFAULT_LORA = "Flux_2-Turbo-LoRA_comfyui.safetensors"

# SD3.5 defaults
DEFAULT_SD3_CHECKPOINT = "sd3.5_medium.safetensors"
DEFAULT_SD3_CLIP_L = "clip_l.safetensors"
DEFAULT_SD3_CLIP_G = "clip_g.safetensors"
DEFAULT_PIPELINE = "sd3"  # "flux2" or "sd3"


# --- Workflow templates -------------------------------------------------------

def _txt2img_workflow(
    prompt: str,
    *,
    seed: int = 0,
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    cfg: float = 1.0,
    denoise: float = 1.0,
    unet: str = DEFAULT_UNET,
    clip: str = DEFAULT_CLIP,
    vae: str = DEFAULT_VAE,
    lora: str | None = DEFAULT_LORA,
    lora_strength: float = 1.0,
    filename_prefix: str = "fh_gen",
) -> dict[str, Any]:
    """Build a ComfyUI workflow dict for text-to-image with Flux 2."""
    wf: dict[str, Any] = {}

    # 1 — Load UNET
    wf["1"] = {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": unet,
            "weight_dtype": DEFAULT_WEIGHT_DTYPE,
        },
    }

    # 2 — Load CLIP (Mistral text encoder for Flux 2)
    wf["2"] = {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": clip,
            "type": "flux2",
        },
    }

    # 3 — Load VAE
    wf["3"] = {
        "class_type": "VAELoader",
        "inputs": {
            "vae_name": vae,
        },
    }

    # Node IDs track: model output starts at node 1, clip at 2
    model_source = ["1", 0]
    clip_source = ["2", 0]

    # 4 — Optional: Load LoRA (turbo acceleration)
    if lora:
        wf["4"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": model_source,
                "clip": clip_source,
                "lora_name": lora,
                "strength_model": lora_strength,
                "strength_clip": lora_strength,
            },
        }
        model_source = ["4", 0]
        clip_source = ["4", 1]

    # 5 — CLIP text encode (positive prompt)
    wf["5"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": clip_source,
            "text": prompt,
        },
    }

    # 6 — Empty latent image
    wf["6"] = {
        "class_type": "EmptyFlux2LatentImage",
        "inputs": {
            "width": width,
            "height": height,
            "batch_size": 1,
        },
    }

    # 7 — KSampler
    wf["7"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": model_source,
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": "euler",
            "scheduler": "simple",
            "positive": ["5", 0],
            "negative": ["5", 0],  # Flux 2 doesn't use negative — pass same
            "latent_image": ["6", 0],
            "denoise": denoise,
        },
    }

    # 8 — VAE Decode
    wf["8"] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["7", 0],
            "vae": ["3", 0],
        },
    }

    # 9 — Save Image
    wf["9"] = {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["8", 0],
            "filename_prefix": filename_prefix,
        },
    }

    return wf


def _img2img_workflow(
    prompt: str,
    *,
    input_image: str,
    seed: int = 0,
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    cfg: float = 1.0,
    denoise: float = 0.6,
    unet: str = DEFAULT_UNET,
    clip: str = DEFAULT_CLIP,
    vae: str = DEFAULT_VAE,
    lora: str | None = DEFAULT_LORA,
    lora_strength: float = 1.0,
    filename_prefix: str = "fh_i2i",
) -> dict[str, Any]:
    """Build a ComfyUI workflow dict for image-to-image with Flux 2.

    ``input_image`` is a filename already uploaded to ComfyUI's input dir.
    ``denoise`` controls how much of the original image to preserve
    (0.0 = identical, 1.0 = full regeneration).
    """
    wf: dict[str, Any] = {}

    # 1 — Load UNET
    wf["1"] = {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": unet,
            "weight_dtype": DEFAULT_WEIGHT_DTYPE,
        },
    }

    # 2 — Load CLIP
    wf["2"] = {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": clip,
            "type": "flux2",
        },
    }

    # 3 — Load VAE
    wf["3"] = {
        "class_type": "VAELoader",
        "inputs": {
            "vae_name": vae,
        },
    }

    model_source = ["1", 0]
    clip_source = ["2", 0]

    # 4 — Optional LoRA
    if lora:
        wf["4"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": model_source,
                "clip": clip_source,
                "lora_name": lora,
                "strength_model": lora_strength,
                "strength_clip": lora_strength,
            },
        }
        model_source = ["4", 0]
        clip_source = ["4", 1]

    # 5 — CLIP text encode
    wf["5"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": clip_source,
            "text": prompt,
        },
    }

    # 6 — Load input image
    wf["6"] = {
        "class_type": "LoadImage",
        "inputs": {
            "image": input_image,
        },
    }

    # 7 — Scale image to target dimensions
    wf["7"] = {
        "class_type": "ImageScale",
        "inputs": {
            "image": ["6", 0],
            "upscale_method": "lanczos",
            "width": width,
            "height": height,
            "crop": "center",
        },
    }

    # 8 — VAE Encode (image → latent)
    wf["8"] = {
        "class_type": "VAEEncode",
        "inputs": {
            "pixels": ["7", 0],
            "vae": ["3", 0],
        },
    }

    # 9 — KSampler (img2img via denoise < 1.0)
    wf["9"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": model_source,
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": "euler",
            "scheduler": "simple",
            "positive": ["5", 0],
            "negative": ["5", 0],
            "latent_image": ["8", 0],
            "denoise": denoise,
        },
    }

    # 10 — VAE Decode
    wf["10"] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["9", 0],
            "vae": ["3", 0],
        },
    }

    # 11 — Save Image
    wf["11"] = {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["10", 0],
            "filename_prefix": filename_prefix,
        },
    }

    return wf


# --- SD3.5 workflow templates -------------------------------------------------

def _sd3_txt2img_workflow(
    prompt: str,
    *,
    negative_prompt: str = "",
    seed: int = 0,
    width: int = 1024,
    height: int = 1024,
    steps: int = 28,
    cfg: float = 4.5,
    denoise: float = 1.0,
    checkpoint: str = DEFAULT_SD3_CHECKPOINT,
    clip_l: str = DEFAULT_SD3_CLIP_L,
    clip_g: str = DEFAULT_SD3_CLIP_G,
    filename_prefix: str = "fh_gen",
) -> dict[str, Any]:
    """Build a ComfyUI workflow dict for text-to-image with SD3.5."""
    wf: dict[str, Any] = {}

    # 1 — Load checkpoint (model + vae; clip is loaded separately)
    wf["1"] = {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": checkpoint,
        },
    }

    # 10 — Load CLIP via DualCLIPLoader (SD3.5 Medium has no bundled CLIP)
    wf["10"] = {
        "class_type": "DualCLIPLoader",
        "inputs": {
            "clip_name1": clip_l,
            "clip_name2": clip_g,
            "type": "sd3",
        },
    }

    # 2 — Positive prompt
    wf["2"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["10", 0],
            "text": prompt,
        },
    }

    # 3 — Negative prompt
    wf["3"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["10", 0],
            "text": negative_prompt,
        },
    }

    # 4 — Empty latent image
    wf["4"] = {
        "class_type": "EmptySD3LatentImage",
        "inputs": {
            "width": width,
            "height": height,
            "batch_size": 1,
        },
    }

    # 5 — KSampler
    wf["5"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": ["1", 0],
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": "euler",
            "scheduler": "sgm_uniform",
            "positive": ["2", 0],
            "negative": ["3", 0],
            "latent_image": ["4", 0],
            "denoise": denoise,
        },
    }

    # 6 — VAE Decode
    wf["6"] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["5", 0],
            "vae": ["1", 2],
        },
    }

    # 7 — Save Image
    wf["7"] = {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["6", 0],
            "filename_prefix": filename_prefix,
        },
    }

    return wf


def _sd3_img2img_workflow(
    prompt: str,
    *,
    input_image: str,
    negative_prompt: str = "",
    seed: int = 0,
    width: int = 1024,
    height: int = 1024,
    steps: int = 28,
    cfg: float = 4.5,
    denoise: float = 0.6,
    checkpoint: str = DEFAULT_SD3_CHECKPOINT,
    clip_l: str = DEFAULT_SD3_CLIP_L,
    clip_g: str = DEFAULT_SD3_CLIP_G,
    filename_prefix: str = "fh_i2i",
) -> dict[str, Any]:
    """Build a ComfyUI workflow dict for image-to-image with SD3.5."""
    wf: dict[str, Any] = {}

    # 1 — Load checkpoint
    wf["1"] = {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": checkpoint,
        },
    }

    # 10 — Load CLIP via DualCLIPLoader
    wf["10"] = {
        "class_type": "DualCLIPLoader",
        "inputs": {
            "clip_name1": clip_l,
            "clip_name2": clip_g,
            "type": "sd3",
        },
    }

    # 2 — Positive prompt
    wf["2"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["10", 0],
            "text": prompt,
        },
    }

    # 3 — Negative prompt
    wf["3"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["10", 0],
            "text": negative_prompt,
        },
    }

    # 4 — Load input image
    wf["4"] = {
        "class_type": "LoadImage",
        "inputs": {
            "image": input_image,
        },
    }

    # 5 — Scale image
    wf["5"] = {
        "class_type": "ImageScale",
        "inputs": {
            "image": ["4", 0],
            "upscale_method": "lanczos",
            "width": width,
            "height": height,
            "crop": "center",
        },
    }

    # 6 — VAE Encode
    wf["6"] = {
        "class_type": "VAEEncode",
        "inputs": {
            "pixels": ["5", 0],
            "vae": ["1", 2],
        },
    }

    # 7 — KSampler
    wf["7"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": ["1", 0],
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": "euler",
            "scheduler": "sgm_uniform",
            "positive": ["2", 0],
            "negative": ["3", 0],
            "latent_image": ["6", 0],
            "denoise": denoise,
        },
    }

    # 8 — VAE Decode
    wf["8"] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["7", 0],
            "vae": ["1", 2],
        },
    }

    # 9 — Save Image
    wf["9"] = {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["8", 0],
            "filename_prefix": filename_prefix,
        },
    }

    return wf


# --- API client ---------------------------------------------------------------


@dataclass
class ComfyUIClient:
    """REST client for the ComfyUI API.

    Silent fallback: any error returns ``None`` and the caller uses the
    PIL placeholder instead.
    """

    base_url: str = DEFAULT_BASE_URL
    timeout: int = DEFAULT_TIMEOUT
    enabled: bool = True
    pipeline: str = DEFAULT_PIPELINE  # "flux2" or "sd3"
    # Flux 2 pipeline models
    unet: str = DEFAULT_UNET
    clip: str = DEFAULT_CLIP
    vae: str = DEFAULT_VAE
    lora: str | None = DEFAULT_LORA
    lora_strength: float = 1.0
    # SD3.5 pipeline
    checkpoint: str = DEFAULT_SD3_CHECKPOINT
    _consecutive_errors: int = field(default=0, repr=False)

    # --- Health & discovery --------------------------------------------------

    def is_available(self) -> bool:
        """Quick check: can we reach ComfyUI?"""
        if not self.enabled:
            return False
        try:
            url = f"{self.base_url}/system_stats"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self, folder: str = "diffusion_models") -> list[str]:
        """List model filenames in a ComfyUI model folder."""
        try:
            url = f"{self.base_url}/models/{folder}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return []

    # --- Image generation ----------------------------------------------------

    def txt2img(
        self,
        prompt: str,
        *,
        seed: int = 0,
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg: float = 1.0,
        denoise: float = 1.0,
        filename_prefix: str = "fh_gen",
    ) -> bytes | None:
        """Generate an image from a text prompt. Returns PNG bytes or None."""
        if not self.enabled:
            return None

        if self.pipeline == "sd3":
            workflow = _sd3_txt2img_workflow(
                prompt,
                seed=seed,
                width=width,
                height=height,
                steps=steps,
                cfg=cfg,
                denoise=denoise,
                checkpoint=self.checkpoint,
                filename_prefix=filename_prefix,
            )
        else:
            workflow = _txt2img_workflow(
                prompt,
                seed=seed,
                width=width,
                height=height,
                steps=steps,
                cfg=cfg,
                denoise=denoise,
                unet=self.unet,
                clip=self.clip,
                vae=self.vae,
                lora=self.lora,
                lora_strength=self.lora_strength,
                filename_prefix=filename_prefix,
            )
        return self._submit_and_wait(workflow)

    def img2img(
        self,
        prompt: str,
        *,
        input_image: str,
        seed: int = 0,
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg: float = 1.0,
        denoise: float = 0.6,
        filename_prefix: str = "fh_i2i",
    ) -> bytes | None:
        """Generate a variation of an input image. Returns PNG bytes or None.

        ``input_image`` must already be uploaded to ComfyUI's input directory.
        """
        if not self.enabled:
            return None

        if self.pipeline == "sd3":
            workflow = _sd3_img2img_workflow(
                prompt,
                input_image=input_image,
                seed=seed,
                width=width,
                height=height,
                steps=steps,
                cfg=cfg,
                denoise=denoise,
                checkpoint=self.checkpoint,
                filename_prefix=filename_prefix,
            )
        else:
            workflow = _img2img_workflow(
                prompt,
                input_image=input_image,
                seed=seed,
                width=width,
                height=height,
                steps=steps,
                cfg=cfg,
                denoise=denoise,
                unet=self.unet,
                clip=self.clip,
                vae=self.vae,
                lora=self.lora,
                lora_strength=self.lora_strength,
                filename_prefix=filename_prefix,
            )
        return self._submit_and_wait(workflow)

    def upload_image(
        self,
        image_bytes: bytes,
        filename: str,
    ) -> str | None:
        """Upload an image to ComfyUI's input directory.

        Returns the filename on success (may be renamed to avoid
        collisions), or None on failure.
        """
        if not self.enabled:
            return None
        try:
            return self._upload(image_bytes, filename)
        except Exception as exc:
            self._record_error(exc)
            return None

    # --- Core API plumbing ---------------------------------------------------

    def _submit_and_wait(self, workflow: dict) -> bytes | None:
        """Submit workflow, poll until done, download result image."""
        try:
            prompt_id = self._queue_prompt(workflow)
            if not prompt_id:
                return None

            output_info = self._poll_until_done(prompt_id)
            if not output_info:
                return None

            image_data = self._download_image(output_info)
            if image_data:
                self._consecutive_errors = 0
            return image_data

        except Exception as exc:
            self._record_error(exc)
            return None

    def _queue_prompt(self, workflow: dict) -> str | None:
        """POST /prompt — returns the prompt_id."""
        url = f"{self.base_url}/prompt"
        payload = json.dumps({"prompt": workflow}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if "error" in data:
            log.warning("ComfyUI rejected prompt: %s", data["error"])
            return None

        return data.get("prompt_id")

    def _poll_until_done(self, prompt_id: str) -> dict | None:
        """Poll /history/{prompt_id} until the job completes.

        Returns the output info dict with filename/subfolder/type, or
        None on timeout.
        """
        deadline = time.monotonic() + self.timeout
        url = f"{self.base_url}/history/{prompt_id}"

        while time.monotonic() < deadline:
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    history = json.loads(resp.read().decode("utf-8"))

                if prompt_id in history:
                    entry = history[prompt_id]
                    outputs = entry.get("outputs", {})
                    # Find the SaveImage node's output
                    for _node_id, node_output in outputs.items():
                        images = node_output.get("images", [])
                        if images:
                            return images[0]  # {filename, subfolder, type}

            except Exception:
                pass  # transient — keep polling

            time.sleep(POLL_INTERVAL)

        log.warning("ComfyUI prompt %s timed out after %ds", prompt_id, self.timeout)
        return None

    def _download_image(self, output_info: dict) -> bytes | None:
        """GET /view — download the generated image as bytes."""
        filename = output_info.get("filename", "")
        subfolder = output_info.get("subfolder", "")
        img_type = output_info.get("type", "output")

        params = urllib.request.quote(filename)
        url = f"{self.base_url}/view?filename={params}&type={img_type}"
        if subfolder:
            url += f"&subfolder={urllib.request.quote(subfolder)}"

        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()

    def _upload(self, image_bytes: bytes, filename: str) -> str | None:
        """POST /upload/image — multipart form upload."""
        import io
        boundary = "----ComfyUIBoundary"
        body = io.BytesIO()

        # File part
        body.write(f"--{boundary}\r\n".encode())
        body.write(
            f'Content-Disposition: form-data; name="image"; '
            f'filename="{filename}"\r\n'.encode()
        )
        body.write(b"Content-Type: image/png\r\n\r\n")
        body.write(image_bytes)
        body.write(b"\r\n")

        # Overwrite part
        body.write(f"--{boundary}\r\n".encode())
        body.write(b'Content-Disposition: form-data; name="overwrite"\r\n\r\n')
        body.write(b"true\r\n")

        body.write(f"--{boundary}--\r\n".encode())

        content = body.getvalue()
        url = f"{self.base_url}/upload/image"
        req = urllib.request.Request(
            url,
            data=content,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(content)),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("name")

    def _record_error(self, exc: Exception) -> None:
        """Track consecutive errors; auto-disable after threshold."""
        self._consecutive_errors += 1
        if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            log.warning(
                "ComfyUI disabled after %d consecutive errors (last: %s)",
                self._consecutive_errors,
                exc,
            )
            self.enabled = False
        else:
            log.debug(
                "ComfyUI call failed (attempt %d, silent fallback): %s",
                self._consecutive_errors,
                exc,
            )


# --- Prompt builders for game visuals ----------------------------------------


def face_prompt(
    role: str = "other",
    age_group: str = "adult",
    build: str = "athletic",
    gender_presentation: str = "masculine",
) -> str:
    """Build a text prompt for face portrait generation."""
    age_map = {
        "youth": "young person in their late teens",
        "adult": "adult in their mid-twenties",
        "veteran": "person in their mid-thirties",
    }
    build_map = {
        "lean": "lean build",
        "athletic": "athletic build",
        "stocky": "stocky muscular build",
    }
    age_desc = age_map.get(age_group, "adult")
    build_desc = build_map.get(build, "athletic build")

    return (
        f"portrait photograph of a {age_desc}, {build_desc}, "
        f"{gender_presentation} presenting, football player, "
        f"professional headshot, neutral background, "
        f"natural lighting, detailed face, looking at camera"
    )


def background_prompt(location: str, custom: str | None = None) -> str:
    """Build a text prompt for background generation."""
    from .visual import BACKGROUND_PROMPTS
    base = custom or BACKGROUND_PROMPTS.get(location, f"{location}, atmospheric")
    return f"{base}, high quality, detailed environment, cinematic lighting"


# --- Serialisable config -----------------------------------------------------


def comfyui_config_to_dict(client: ComfyUIClient) -> dict[str, Any]:
    return {
        "base_url": client.base_url,
        "timeout": client.timeout,
        "enabled": client.enabled,
        "pipeline": client.pipeline,
        "unet": client.unet,
        "clip": client.clip,
        "vae": client.vae,
        "lora": client.lora,
        "lora_strength": client.lora_strength,
        "checkpoint": client.checkpoint,
    }


def comfyui_config_from_dict(d: Mapping[str, Any]) -> ComfyUIClient:
    return ComfyUIClient(
        base_url=str(d.get("base_url", DEFAULT_BASE_URL)),
        timeout=int(d.get("timeout", DEFAULT_TIMEOUT)),
        enabled=bool(d.get("enabled", True)),
        pipeline=str(d.get("pipeline", DEFAULT_PIPELINE)),
        unet=str(d.get("unet", DEFAULT_UNET)),
        clip=str(d.get("clip", DEFAULT_CLIP)),
        vae=str(d.get("vae", DEFAULT_VAE)),
        lora=d.get("lora", DEFAULT_LORA),
        lora_strength=float(d.get("lora_strength", 1.0)),
        checkpoint=str(d.get("checkpoint", DEFAULT_SD3_CHECKPOINT)),
    )
