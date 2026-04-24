"""Tests for game.engine.comfyui — ComfyUI API client and workflow builders."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from threading import Thread

import pytest
from PIL import Image

from engine.comfyui import (
    DEFAULT_BASE_URL,
    DEFAULT_CLIP,
    DEFAULT_LORA,
    DEFAULT_PIPELINE,
    DEFAULT_SD3_CHECKPOINT,
    DEFAULT_SD3_CLIP_G,
    DEFAULT_SD3_CLIP_L,
    DEFAULT_UNET,
    DEFAULT_VAE,
    MAX_CONSECUTIVE_ERRORS,
    ComfyUIClient,
    _img2img_workflow,
    _sd3_img2img_workflow,
    _sd3_txt2img_workflow,
    _txt2img_workflow,
    background_prompt,
    comfyui_config_from_dict,
    comfyui_config_to_dict,
    face_prompt,
)


# ── Workflow builders ────────────────────────────────────────────────


class TestTxt2ImgWorkflow:
    def test_has_required_nodes(self):
        wf = _txt2img_workflow("a portrait")
        assert "1" in wf  # UNETLoader
        assert "2" in wf  # CLIPLoader
        assert "3" in wf  # VAELoader
        assert "5" in wf  # CLIPTextEncode
        assert "7" in wf  # KSampler
        assert "9" in wf  # SaveImage

    def test_prompt_in_clip_encode(self):
        wf = _txt2img_workflow("a football player portrait")
        assert wf["5"]["inputs"]["text"] == "a football player portrait"

    def test_seed_propagated(self):
        wf = _txt2img_workflow("test", seed=42)
        assert wf["7"]["inputs"]["seed"] == 42

    def test_dimensions(self):
        wf = _txt2img_workflow("test", width=768, height=1024)
        assert wf["6"]["inputs"]["width"] == 768
        assert wf["6"]["inputs"]["height"] == 1024

    def test_lora_included_by_default(self):
        wf = _txt2img_workflow("test")
        assert "4" in wf
        assert wf["4"]["class_type"] == "LoraLoader"

    def test_no_lora(self):
        wf = _txt2img_workflow("test", lora=None)
        assert "4" not in wf
        # Model source should be directly from UNETLoader
        assert wf["7"]["inputs"]["model"] == ["1", 0]

    def test_correct_clip_type(self):
        wf = _txt2img_workflow("test")
        assert wf["2"]["inputs"]["type"] == "flux2"


class TestImg2ImgWorkflow:
    def test_has_load_and_encode(self):
        wf = _img2img_workflow("test", input_image="photo.png")
        assert wf["6"]["class_type"] == "LoadImage"
        assert wf["6"]["inputs"]["image"] == "photo.png"
        assert wf["8"]["class_type"] == "VAEEncode"

    def test_denoise_param(self):
        wf = _img2img_workflow("test", input_image="photo.png", denoise=0.4)
        assert wf["9"]["inputs"]["denoise"] == 0.4

    def test_image_scaling(self):
        wf = _img2img_workflow(
            "test", input_image="photo.png", width=512, height=512
        )
        assert wf["7"]["class_type"] == "ImageScale"
        assert wf["7"]["inputs"]["width"] == 512


# ── SD3.5 Workflow builders ──────────────────────────────────────────


class TestSD3Txt2ImgWorkflow:
    def test_has_required_nodes(self):
        wf = _sd3_txt2img_workflow("a portrait")
        assert wf["1"]["class_type"] == "CheckpointLoaderSimple"
        assert wf["10"]["class_type"] == "DualCLIPLoader"  # separate CLIP
        assert wf["2"]["class_type"] == "CLIPTextEncode"  # positive
        assert wf["3"]["class_type"] == "CLIPTextEncode"  # negative
        assert wf["4"]["class_type"] == "EmptySD3LatentImage"
        assert wf["5"]["class_type"] == "KSampler"
        assert wf["7"]["class_type"] == "SaveImage"

    def test_prompt_in_clip_encode(self):
        wf = _sd3_txt2img_workflow("a football player portrait")
        assert wf["2"]["inputs"]["text"] == "a football player portrait"

    def test_negative_prompt(self):
        wf = _sd3_txt2img_workflow("test", negative_prompt="blurry")
        assert wf["3"]["inputs"]["text"] == "blurry"

    def test_clip_from_dual_loader(self):
        wf = _sd3_txt2img_workflow("test")
        assert wf["2"]["inputs"]["clip"] == ["10", 0]
        assert wf["3"]["inputs"]["clip"] == ["10", 0]
        assert wf["10"]["inputs"]["clip_name1"] == DEFAULT_SD3_CLIP_L
        assert wf["10"]["inputs"]["clip_name2"] == DEFAULT_SD3_CLIP_G
        assert wf["10"]["inputs"]["type"] == "sd3"

    def test_separate_positive_negative(self):
        wf = _sd3_txt2img_workflow("test")
        assert wf["5"]["inputs"]["positive"] == ["2", 0]
        assert wf["5"]["inputs"]["negative"] == ["3", 0]

    def test_seed_propagated(self):
        wf = _sd3_txt2img_workflow("test", seed=42)
        assert wf["5"]["inputs"]["seed"] == 42

    def test_checkpoint_default(self):
        wf = _sd3_txt2img_workflow("test")
        assert wf["1"]["inputs"]["ckpt_name"] == DEFAULT_SD3_CHECKPOINT

    def test_vae_from_checkpoint(self):
        wf = _sd3_txt2img_workflow("test")
        assert wf["6"]["inputs"]["vae"] == ["1", 2]


class TestSD3Img2ImgWorkflow:
    def test_has_load_and_encode(self):
        wf = _sd3_img2img_workflow("test", input_image="photo.png")
        assert wf["4"]["class_type"] == "LoadImage"
        assert wf["4"]["inputs"]["image"] == "photo.png"
        assert wf["6"]["class_type"] == "VAEEncode"
        assert wf["10"]["class_type"] == "DualCLIPLoader"

    def test_denoise_param(self):
        wf = _sd3_img2img_workflow("test", input_image="photo.png", denoise=0.4)
        assert wf["7"]["inputs"]["denoise"] == 0.4


# ── Prompt builders ──────────────────────────────────────────────────


class TestFacePrompt:
    def test_includes_key_descriptors(self):
        p = face_prompt(age_group="youth", build="lean", gender_presentation="feminine")
        assert "late teens" in p
        assert "lean" in p
        assert "feminine" in p
        assert "football" in p

    def test_default_is_athletic_adult(self):
        p = face_prompt()
        assert "mid-twenties" in p
        assert "athletic" in p


class TestBackgroundPrompt:
    def test_known_location(self):
        p = background_prompt("locker_room")
        assert "locker room" in p
        assert "cinematic" in p

    def test_custom_override(self):
        p = background_prompt("custom_place", custom="rainy street at night")
        assert "rainy street" in p


# ── ComfyUIClient (no server) ───────────────────────────────────────


class TestComfyUIClientOffline:
    def test_disabled_returns_none(self):
        client = ComfyUIClient(enabled=False)
        assert client.txt2img("test") is None
        assert client.img2img("test", input_image="x.png") is None

    def test_unavailable_returns_none(self):
        client = ComfyUIClient(base_url="http://localhost:59999", timeout=1)
        assert client.txt2img("test") is None

    def test_is_available_when_disabled(self):
        client = ComfyUIClient(enabled=False)
        assert not client.is_available()

    def test_is_available_when_no_server(self):
        client = ComfyUIClient(base_url="http://localhost:59999", timeout=1)
        assert not client.is_available()

    def test_list_models_when_no_server(self):
        client = ComfyUIClient(base_url="http://localhost:59999", timeout=1)
        assert client.list_models() == []

    def test_auto_disable_after_consecutive_errors(self):
        client = ComfyUIClient(base_url="http://localhost:59999", timeout=1)
        assert client.enabled is True

        for _ in range(MAX_CONSECUTIVE_ERRORS):
            client.txt2img("test")

        assert client.enabled is False


# ── ComfyUIClient with mock server ──────────────────────────────────

# Create a tiny 8x8 PNG for the mock to return.
_TINY_PNG = BytesIO()
Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(_TINY_PNG, "PNG")
_TINY_PNG_BYTES = _TINY_PNG.getvalue()


class _MockComfyHandler(BaseHTTPRequestHandler):
    """Minimal mock of the ComfyUI REST API."""

    prompt_id = "test-prompt-123"

    def do_GET(self):
        if self.path == "/system_stats":
            self._json_response({"system": {"os": "test"}})
        elif self.path.startswith("/models/"):
            folder = self.path.split("/models/")[1]
            if folder == "diffusion_models":
                self._json_response([DEFAULT_UNET])
            else:
                self._json_response([])
        elif self.path.startswith("/history/"):
            pid = self.path.split("/history/")[1]
            self._json_response({
                pid: {
                    "outputs": {
                        "9": {
                            "images": [
                                {
                                    "filename": "result.png",
                                    "subfolder": "",
                                    "type": "output",
                                }
                            ]
                        }
                    }
                }
            })
        elif self.path.startswith("/view"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(_TINY_PNG_BYTES)))
            self.end_headers()
            self.wfile.write(_TINY_PNG_BYTES)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/prompt":
            content_len = int(self.headers.get("Content-Length", 0))
            self.rfile.read(content_len)
            self._json_response(
                {"prompt_id": self.prompt_id, "number": 1}
            )
        elif self.path == "/upload/image":
            content_len = int(self.headers.get("Content-Length", 0))
            self.rfile.read(content_len)
            self._json_response({"name": "uploaded.png", "subfolder": "", "type": "input"})
        else:
            self.send_error(404)

    def _json_response(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def mock_comfy():
    """Start a local mock ComfyUI server for the test module."""
    server = HTTPServer(("127.0.0.1", 0), _MockComfyHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


class TestComfyUIClientWithServer:
    def test_is_available(self, mock_comfy):
        client = ComfyUIClient(base_url=mock_comfy)
        assert client.is_available()

    def test_list_models(self, mock_comfy):
        client = ComfyUIClient(base_url=mock_comfy)
        models = client.list_models("diffusion_models")
        assert DEFAULT_UNET in models

    def test_txt2img_returns_image_bytes(self, mock_comfy):
        client = ComfyUIClient(base_url=mock_comfy)
        result = client.txt2img("portrait of a footballer", seed=42)
        assert result is not None
        # Verify it's valid PNG data
        img = Image.open(BytesIO(result))
        assert img.size == (8, 8)

    def test_img2img_returns_image_bytes(self, mock_comfy):
        client = ComfyUIClient(base_url=mock_comfy)
        result = client.img2img(
            "variation of portrait",
            input_image="test.png",
            seed=42,
            denoise=0.5,
        )
        assert result is not None
        img = Image.open(BytesIO(result))
        assert img.size == (8, 8)

    def test_upload_image(self, mock_comfy):
        client = ComfyUIClient(base_url=mock_comfy)
        result = client.upload_image(_TINY_PNG_BYTES, "test_upload.png")
        assert result == "uploaded.png"

    def test_success_resets_error_count(self, mock_comfy):
        client = ComfyUIClient(base_url=mock_comfy)
        client._consecutive_errors = MAX_CONSECUTIVE_ERRORS - 1
        result = client.txt2img("test", seed=1)
        assert result is not None
        assert client._consecutive_errors == 0
        assert client.enabled is True


# ── Config serialisation ────────────────────────────────────────────


class TestComfyUIConfig:
    def test_roundtrip(self):
        client = ComfyUIClient(
            base_url="http://example.com:9999",
            timeout=60,
            enabled=True,
            pipeline="flux2",
            unet="my-unet.safetensors",
            clip="my-clip.safetensors",
            vae="my-vae.safetensors",
            lora="my-lora.safetensors",
            lora_strength=0.8,
            checkpoint="my-ckpt.safetensors",
        )
        d = comfyui_config_to_dict(client)
        restored = comfyui_config_from_dict(d)
        assert restored.base_url == client.base_url
        assert restored.timeout == client.timeout
        assert restored.enabled == client.enabled
        assert restored.pipeline == client.pipeline
        assert restored.unet == client.unet
        assert restored.clip == client.clip
        assert restored.vae == client.vae
        assert restored.lora == client.lora
        assert restored.lora_strength == client.lora_strength
        assert restored.checkpoint == client.checkpoint

    def test_defaults_on_empty_dict(self):
        client = comfyui_config_from_dict({})
        assert client.base_url == DEFAULT_BASE_URL
        assert client.enabled is True
        assert client.pipeline == DEFAULT_PIPELINE
        assert client.unet == DEFAULT_UNET
        assert client.checkpoint == DEFAULT_SD3_CHECKPOINT
