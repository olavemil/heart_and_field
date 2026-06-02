"""Tests for ComfyUIImageProducer (Phase 21A)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.background_generator import (
    ComfyUIImageProducer,
    PlaceholderImageProducer,
    _BG_PROMPT_PREFIX,
    _NODE_PROMPT_HINTS,
    _VARIANT_PROMPT_SUFFIX,
)
from engine.background_pool import (
    Era,
    LocationDescriptor,
    LocationKind,
    MoodTone,
    SceneGraphSpec,
    Socioeconomic,
)


# --- Helpers ---------------------------------------------------------------

# Minimal valid PNG header (8 bytes) for test assertions.
FAKE_PNG = b"\x89PNG\r\n\x1a\nfake_image_data"


def _descriptor(**overrides) -> LocationDescriptor:
    base = dict(
        kind=LocationKind.CAFE,
        era=Era.MODERN,
        socioeconomic=Socioeconomic.COMFORTABLE,
        mood=MoodTone.WARM,
    )
    base.update(overrides)
    return LocationDescriptor(**base)


def _spec() -> SceneGraphSpec:
    return SceneGraphSpec(
        spec_id="cafe",
        kind=LocationKind.CAFE,
        nodes=("street_view", "bar_counter", "dining_area"),
        adjacency=(
            ("street_view", "bar_counter"),
            ("bar_counter", "dining_area"),
        ),
        entry_nodes=("street_view",),
    )


def _mock_client(
    *,
    txt2img_result: bytes | None = FAKE_PNG,
    img2img_result: bytes | None = FAKE_PNG,
    upload_result: str | None = "uploaded.png",
) -> MagicMock:
    client = MagicMock()
    client.txt2img.return_value = txt2img_result
    client.img2img.return_value = img2img_result
    client.upload_image.return_value = upload_result
    return client


# --- Prompt construction ---------------------------------------------------


class TestBuildPrompt:
    def test_includes_descriptor_fragment(self):
        desc = _descriptor()
        prompt = ComfyUIImageProducer._build_prompt(desc, "bar_counter")
        assert desc.to_prompt_fragment() in prompt

    def test_includes_prefix(self):
        desc = _descriptor()
        prompt = ComfyUIImageProducer._build_prompt(desc, "bar_counter")
        assert prompt.startswith(_BG_PROMPT_PREFIX)

    def test_known_node_uses_hint(self):
        desc = _descriptor()
        prompt = ComfyUIImageProducer._build_prompt(desc, "bar_counter")
        assert _NODE_PROMPT_HINTS["bar_counter"] in prompt

    def test_unknown_node_falls_back_to_readable_name(self):
        desc = _descriptor()
        prompt = ComfyUIImageProducer._build_prompt(desc, "secret_room")
        assert "secret room" in prompt


# --- Fresh generation (txt2img) --------------------------------------------


class TestProduceFresh:
    def test_txt2img_called_for_first_node(self, tmp_path: Path):
        client = _mock_client()
        producer = ComfyUIImageProducer(client=client)
        out = tmp_path / "bg.png"
        producer.produce(
            descriptor=_descriptor(),
            spec=_spec(),
            node_name="street_view",
            seed=42,
            anchor_path=None,
            out_path=out,
            variant_index=0,
        )
        client.txt2img.assert_called_once()
        assert out.exists()
        assert out.read_bytes() == FAKE_PNG

    def test_txt2img_params(self, tmp_path: Path):
        client = _mock_client()
        producer = ComfyUIImageProducer(client=client, width=1024, height=576)
        out = tmp_path / "bg.png"
        producer.produce(
            descriptor=_descriptor(),
            spec=_spec(),
            node_name="street_view",
            seed=99,
            anchor_path=None,
            out_path=out,
        )
        call_kwargs = client.txt2img.call_args
        assert call_kwargs.kwargs["seed"] == 99
        assert call_kwargs.kwargs["width"] == 1024
        assert call_kwargs.kwargs["height"] == 576
        assert call_kwargs.kwargs["denoise"] == 1.0


# --- Anchored generation (img2img) -----------------------------------------


class TestProduceAnchored:
    def test_img2img_called_with_anchor(self, tmp_path: Path):
        client = _mock_client()
        producer = ComfyUIImageProducer(client=client)
        anchor = tmp_path / "anchor.png"
        anchor.write_bytes(FAKE_PNG)
        out = tmp_path / "room.png"
        producer.produce(
            descriptor=_descriptor(),
            spec=_spec(),
            node_name="bar_counter",
            seed=7,
            anchor_path=anchor,
            out_path=out,
            variant_index=0,
        )
        client.upload_image.assert_called_once()
        client.img2img.assert_called_once()
        call_kwargs = client.img2img.call_args
        assert call_kwargs.kwargs["denoise"] == producer.anchor_denoise
        assert out.exists()

    def test_anchor_upload_failure_falls_back(self, tmp_path: Path):
        client = _mock_client(upload_result=None)
        producer = ComfyUIImageProducer(client=client)
        anchor = tmp_path / "anchor.png"
        anchor.write_bytes(FAKE_PNG)
        out = tmp_path / "room.png"
        producer.produce(
            descriptor=_descriptor(),
            spec=_spec(),
            node_name="bar_counter",
            seed=7,
            anchor_path=anchor,
            out_path=out,
            variant_index=0,
        )
        # Upload failed → img2img not called → falls back to placeholder
        client.img2img.assert_not_called()
        assert out.exists()  # placeholder wrote it


# --- Variant generation (img2img low denoise) ------------------------------


class TestProduceVariant:
    def test_variant_uses_low_denoise(self, tmp_path: Path):
        client = _mock_client()
        producer = ComfyUIImageProducer(client=client)
        primary = tmp_path / "primary.png"
        primary.write_bytes(FAKE_PNG)
        out = tmp_path / "variant.png"
        producer.produce(
            descriptor=_descriptor(),
            spec=_spec(),
            node_name="bar_counter",
            seed=100,
            anchor_path=primary,
            out_path=out,
            variant_index=1,
        )
        call_kwargs = client.img2img.call_args
        assert call_kwargs.kwargs["denoise"] == producer.variant_denoise
        assert _VARIANT_PROMPT_SUFFIX in call_kwargs.args[0]

    def test_variant_without_anchor_uses_out_path(self, tmp_path: Path):
        """When variant_index > 0 but anchor_path is None, the producer
        uses out_path as the anchor (the primary image at the same path)."""
        client = _mock_client()
        producer = ComfyUIImageProducer(client=client)
        out = tmp_path / "variant.png"
        # out_path doesn't exist → upload_anchor returns None → fallback
        producer.produce(
            descriptor=_descriptor(),
            spec=_spec(),
            node_name="bar_counter",
            seed=100,
            anchor_path=None,
            out_path=out,
            variant_index=1,
        )
        # anchor_path was None, so produce uses out_path as anchor
        # out_path doesn't exist → upload returns None → fallback
        assert out.exists()  # placeholder wrote it


# --- Fallback behaviour ----------------------------------------------------


class TestFallback:
    def test_comfyui_returns_none_falls_back_to_placeholder(self, tmp_path: Path):
        client = _mock_client(txt2img_result=None)
        producer = ComfyUIImageProducer(client=client)
        out = tmp_path / "bg.png"
        producer.produce(
            descriptor=_descriptor(),
            spec=_spec(),
            node_name="street_view",
            seed=42,
            anchor_path=None,
            out_path=out,
        )
        assert out.exists()
        # Placeholder writes a larger file with PIL; just check it's not
        # the fake PNG.
        assert out.read_bytes() != FAKE_PNG

    def test_creates_parent_directories(self, tmp_path: Path):
        client = _mock_client()
        producer = ComfyUIImageProducer(client=client)
        out = tmp_path / "deep" / "nested" / "bg.png"
        producer.produce(
            descriptor=_descriptor(),
            spec=_spec(),
            node_name="street_view",
            seed=42,
            anchor_path=None,
            out_path=out,
        )
        assert out.exists()
