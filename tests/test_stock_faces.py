"""Tests for engine.stock_faces — stock face pool."""

import json
from pathlib import Path

import pytest
from PIL import Image

from engine.stock_faces import StockFace, StockFacePool


@pytest.fixture()
def pool_dir(tmp_path: Path) -> Path:
    d = tmp_path / "stock_faces"
    d.mkdir()
    return d


def _make_face_png(path: Path) -> None:
    """Write a tiny 4x4 PNG."""
    img = Image.new("RGBA", (4, 4), (200, 180, 160, 255))
    img.save(str(path), "PNG")


class TestStockFacePool:
    def test_load_empty(self, pool_dir: Path) -> None:
        pool = StockFacePool.load(pool_dir)
        assert pool.empty
        assert pool.select("masculine", seed=42) is None

    def test_load_manifest(self, pool_dir: Path) -> None:
        _make_face_png(pool_dir / "m_adult_000.png")
        _make_face_png(pool_dir / "f_adult_000.png")
        manifest = {
            "version": 1,
            "faces": [
                {"filename": "m_adult_000.png", "gender_presentation": "masculine", "age_bucket": "adult"},
                {"filename": "f_adult_000.png", "gender_presentation": "feminine", "age_bucket": "adult"},
            ],
        }
        (pool_dir / "manifest.json").write_text(json.dumps(manifest))
        pool = StockFacePool.load(pool_dir)
        assert not pool.empty
        assert len(pool.faces) == 2

    def test_select_matches_gender(self, pool_dir: Path) -> None:
        _make_face_png(pool_dir / "m.png")
        _make_face_png(pool_dir / "f.png")
        manifest = {
            "version": 1,
            "faces": [
                {"filename": "m.png", "gender_presentation": "masculine", "age_bucket": "adult"},
                {"filename": "f.png", "gender_presentation": "feminine", "age_bucket": "adult"},
            ],
        }
        (pool_dir / "manifest.json").write_text(json.dumps(manifest))
        pool = StockFacePool.load(pool_dir)

        path = pool.select("masculine", seed=99)
        assert path is not None
        assert path.name == "m.png"

        path = pool.select("feminine", seed=99)
        assert path is not None
        assert path.name == "f.png"

    def test_select_falls_back_to_any(self, pool_dir: Path) -> None:
        _make_face_png(pool_dir / "m.png")
        manifest = {
            "version": 1,
            "faces": [
                {"filename": "m.png", "gender_presentation": "masculine", "age_bucket": "adult"},
            ],
        }
        (pool_dir / "manifest.json").write_text(json.dumps(manifest))
        pool = StockFacePool.load(pool_dir)
        # No androgynous faces — falls back to masculine.
        path = pool.select("androgynous", seed=42)
        assert path is not None
        assert path.name == "m.png"

    def test_select_deterministic(self, pool_dir: Path) -> None:
        for i in range(5):
            _make_face_png(pool_dir / f"m_{i}.png")
        manifest = {
            "version": 1,
            "faces": [
                {"filename": f"m_{i}.png", "gender_presentation": "masculine", "age_bucket": "adult"}
                for i in range(5)
            ],
        }
        (pool_dir / "manifest.json").write_text(json.dumps(manifest))
        pool = StockFacePool.load(pool_dir)
        a = pool.select("masculine", seed=123)
        b = pool.select("masculine", seed=123)
        assert a == b
        # Different seed may pick a different face.
        c = pool.select("masculine", seed=999)
        # (Not necessarily different with only 5 faces, but the API works.)
        assert c is not None

    def test_missing_file_skipped(self, pool_dir: Path) -> None:
        _make_face_png(pool_dir / "exists.png")
        manifest = {
            "version": 1,
            "faces": [
                {"filename": "exists.png", "gender_presentation": "masculine", "age_bucket": "adult"},
                {"filename": "gone.png", "gender_presentation": "masculine", "age_bucket": "adult"},
            ],
        }
        (pool_dir / "manifest.json").write_text(json.dumps(manifest))
        pool = StockFacePool.load(pool_dir)
        assert len(pool.faces) == 1

    def test_save_roundtrip(self, pool_dir: Path) -> None:
        pool = StockFacePool(root=pool_dir)
        _make_face_png(pool_dir / "test.png")
        face = StockFace(filename="test.png", gender_presentation="masculine", age_bucket="young")
        pool.add(face)
        pool.save()

        loaded = StockFacePool.load(pool_dir)
        assert len(loaded.faces) == 1
        assert loaded.faces[0].filename == "test.png"
        assert loaded.faces[0].gender_presentation == "masculine"
        assert loaded.faces[0].age_bucket == "young"

    def test_corrupt_manifest_returns_empty(self, pool_dir: Path) -> None:
        (pool_dir / "manifest.json").write_text("not json!!!")
        pool = StockFacePool.load(pool_dir)
        assert pool.empty

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        pool = StockFacePool.load(tmp_path / "nonexistent")
        assert pool.empty
