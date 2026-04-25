"""Tests for engine.sprite_generator using a mock ComfyUIClient.

The real ComfyUI is not touched — we stub ``txt2img``, ``img2img``, and
``upload_image`` on the client so tests run in any environment.
"""

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from engine.comfyui import ComfyUIClient
from engine.sprite_generator import (
    DEFAULT_EXPRESSIONS,
    SpriteGenerationConfig,
    SpriteGenerationError,
    SpriteGenerator,
)
from engine.sprite_pool import (
    AgeBucket,
    Build,
    CharacterDescriptor,
    GenderPresentation,
    SkinTone,
    SpriteManifest,
)


# --- Helpers ----------------------------------------------------------------


def _png_bytes(colour: tuple[int, int, int] = (128, 64, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), colour).save(buf, "PNG")
    return buf.getvalue()


def _descriptor() -> CharacterDescriptor:
    return CharacterDescriptor(
        gender_presentation=GenderPresentation.MASCULINE,
        age_bucket=AgeBucket.ADULT,
        skin_tone=SkinTone.MEDIUM,
        build=Build.ATHLETIC,
        hair="short_brown",
    )


def _mock_client(success: bool = True) -> MagicMock:
    client = MagicMock(spec=ComfyUIClient)
    client.txt2img.return_value = _png_bytes((50, 100, 150)) if success else None
    client.img2img.return_value = _png_bytes((150, 100, 50)) if success else None
    client.upload_image.return_value = "uploaded_neutral.png" if success else None
    return client


# --- Tests ------------------------------------------------------------------


class TestGenerateSet:
    def test_produces_entry_with_all_expressions(self, tmp_path: Path):
        manifest = SpriteManifest(assets_root=tmp_path)
        client = _mock_client()
        generator = SpriteGenerator(client=client, manifest=manifest)

        entry = generator.generate_set(
            _descriptor(),
            expressions=["neutral", "confident", "warm"],
            seed=42,
        )

        assert entry.variants.keys() == {"neutral", "confident", "warm"}
        assert entry in manifest.entries
        # Files written to disk.
        for path in entry.variants.values():
            assert (tmp_path / path).exists()

    def test_txt2img_called_once_for_neutral(self, tmp_path: Path):
        manifest = SpriteManifest(assets_root=tmp_path)
        client = _mock_client()
        generator = SpriteGenerator(client=client, manifest=manifest)
        generator.generate_set(
            _descriptor(), expressions=["neutral", "warm"], seed=1
        )
        assert client.txt2img.call_count == 1

    def test_img2img_called_per_variant(self, tmp_path: Path):
        manifest = SpriteManifest(assets_root=tmp_path)
        client = _mock_client()
        generator = SpriteGenerator(client=client, manifest=manifest)
        generator.generate_set(
            _descriptor(),
            expressions=["neutral", "confident", "warm", "anxious"],
            seed=1,
        )
        # Three non-neutral expressions → three img2img calls.
        assert client.img2img.call_count == 3

    def test_neutral_uploaded_before_variants(self, tmp_path: Path):
        manifest = SpriteManifest(assets_root=tmp_path)
        client = _mock_client()
        generator = SpriteGenerator(client=client, manifest=manifest)
        generator.generate_set(
            _descriptor(), expressions=["neutral", "warm"], seed=1
        )
        client.upload_image.assert_called_once()

    def test_manifest_persisted(self, tmp_path: Path):
        manifest = SpriteManifest(assets_root=tmp_path)
        client = _mock_client()
        generator = SpriteGenerator(client=client, manifest=manifest)
        generator.generate_set(
            _descriptor(), expressions=["neutral"], seed=1
        )
        reloaded = SpriteManifest.load(tmp_path)
        assert len(reloaded.entries) == 1

    def test_reserved_for_propagates(self, tmp_path: Path):
        manifest = SpriteManifest(assets_root=tmp_path)
        client = _mock_client()
        generator = SpriteGenerator(client=client, manifest=manifest)
        entry = generator.generate_set(
            _descriptor(),
            expressions=["neutral"],
            seed=1,
            reserved_for="player",
        )
        assert entry.reserved_for == "player"

    def test_variant_seeds_differ(self, tmp_path: Path):
        manifest = SpriteManifest(assets_root=tmp_path)
        client = _mock_client()
        generator = SpriteGenerator(client=client, manifest=manifest)
        generator.generate_set(
            _descriptor(),
            expressions=["neutral", "warm", "anxious"],
            seed=100,
        )
        variant_seeds = [
            call.kwargs["seed"] for call in client.img2img.call_args_list
        ]
        assert len(set(variant_seeds)) == len(variant_seeds)


class TestFailureSurfaces:
    def test_neutral_failure_raises(self, tmp_path: Path):
        manifest = SpriteManifest(assets_root=tmp_path)
        client = _mock_client()
        client.txt2img.return_value = None
        generator = SpriteGenerator(client=client, manifest=manifest)
        with pytest.raises(SpriteGenerationError):
            generator.generate_set(_descriptor(), expressions=["neutral"])

    def test_upload_failure_raises(self, tmp_path: Path):
        manifest = SpriteManifest(assets_root=tmp_path)
        client = _mock_client()
        client.upload_image.return_value = None
        generator = SpriteGenerator(client=client, manifest=manifest)
        with pytest.raises(SpriteGenerationError):
            generator.generate_set(
                _descriptor(), expressions=["neutral", "warm"]
            )

    def test_variant_failure_raises(self, tmp_path: Path):
        manifest = SpriteManifest(assets_root=tmp_path)
        client = _mock_client()
        client.img2img.return_value = None
        generator = SpriteGenerator(client=client, manifest=manifest)
        with pytest.raises(SpriteGenerationError):
            generator.generate_set(
                _descriptor(), expressions=["neutral", "warm"]
            )


class TestBgRemover:
    def test_bg_remover_applied_to_saved_image(self, tmp_path: Path):
        manifest = SpriteManifest(assets_root=tmp_path)
        client = _mock_client()
        calls = []

        def fake_bg_remove(data: bytes) -> bytes:
            calls.append(data)
            return _png_bytes((0, 255, 0))

        generator = SpriteGenerator(
            client=client, manifest=manifest, bg_remover=fake_bg_remove
        )
        generator.generate_set(
            _descriptor(), expressions=["neutral"], seed=1
        )
        assert len(calls) == 1  # Called for neutral.

    def test_bg_remover_failure_does_not_break_save(self, tmp_path: Path):
        manifest = SpriteManifest(assets_root=tmp_path)
        client = _mock_client()

        def bad_bg(data: bytes) -> bytes:
            raise RuntimeError("bg broke")

        generator = SpriteGenerator(
            client=client, manifest=manifest, bg_remover=bad_bg
        )
        # Should not raise — warning logged, original data saved.
        entry = generator.generate_set(
            _descriptor(), expressions=["neutral"], seed=1
        )
        assert (tmp_path / entry.neutral_path).exists()
