"""Tests for the sprite descriptor + manifest (engine.sprite_pool)."""

from pathlib import Path

import pytest

from engine.sprite_pool import (
    AgeBucket,
    Build,
    CharacterDescriptor,
    GenderPresentation,
    SkinTone,
    SpriteEntry,
    SpriteManifest,
)


def _descriptor(**overrides) -> CharacterDescriptor:
    base = dict(
        gender_presentation=GenderPresentation.MASCULINE,
        age_bucket=AgeBucket.ADULT,
        skin_tone=SkinTone.MEDIUM,
        build=Build.ATHLETIC,
        hair="short_brown",
    )
    base.update(overrides)
    return CharacterDescriptor(**base)


# --- Descriptor -------------------------------------------------------------


class TestDescriptor:
    def test_bucket_key_stable_across_equivalent_instances(self):
        assert _descriptor().bucket_key() == _descriptor().bucket_key()

    def test_bucket_key_changes_with_each_axis(self):
        baseline = _descriptor().bucket_key()
        assert _descriptor(hair="long_black").bucket_key() != baseline
        assert _descriptor(build=Build.LEAN).bucket_key() != baseline
        assert _descriptor(facial_hair=True).bucket_key() != baseline
        assert _descriptor(glasses=True).bucket_key() != baseline

    def test_to_prompt_fragment_mentions_every_axis(self):
        frag = _descriptor(
            facial_hair=True, glasses=True, skin_tone=SkinTone.DARK
        ).to_prompt_fragment()
        assert "dark skin" in frag
        assert "facial hair" in frag
        assert "glasses" in frag
        assert "masculine presenting" in frag

    def test_round_trip(self):
        d = _descriptor(glasses=True, hair="buzz_black")
        assert CharacterDescriptor.from_dict(d.to_dict()) == d

    def test_short_hash_is_deterministic_hex(self):
        h1 = _descriptor().short_hash()
        h2 = _descriptor().short_hash()
        assert h1 == h2
        assert len(h1) == 8
        int(h1, 16)  # does not raise


# --- Entry / Manifest -------------------------------------------------------


def _entry(manifest: SpriteManifest, **desc_overrides) -> SpriteEntry:
    d = _descriptor(**desc_overrides)
    entry_id = manifest.next_entry_id(d)
    entry = SpriteEntry(
        entry_id=entry_id,
        descriptor=d,
        neutral_path=f"{d.bucket_key()}/{entry_id}/neutral.png",
        variants={"neutral": f"{d.bucket_key()}/{entry_id}/neutral.png"},
    )
    manifest.add_entry(entry)
    return entry


class TestManifestBasics:
    def test_add_and_get(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        e = _entry(mf)
        assert mf.get(e.entry_id) is e
        assert mf.get("nope") is None

    def test_duplicate_entry_id_rejected(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        e = _entry(mf)
        with pytest.raises(ValueError):
            mf.add_entry(e)

    def test_next_entry_id_numbers_within_bucket(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        e1 = _entry(mf)
        e2 = _entry(mf)
        # Different buckets → independent numbering.
        e3 = _entry(mf, hair="long_black")
        assert e1.entry_id.endswith("_0")
        assert e2.entry_id.endswith("_1")
        assert e3.entry_id.endswith("_0")


class TestManifestLookup:
    def test_find_unclaimed_matches_same_bucket(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        _entry(mf)
        found = mf.find_unclaimed(_descriptor())
        assert found is not None

    def test_find_unclaimed_skips_different_bucket(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        _entry(mf)
        found = mf.find_unclaimed(_descriptor(hair="long_black"))
        assert found is None

    def test_find_unclaimed_skips_claimed(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        e = _entry(mf)
        mf.claim(e.entry_id, "player")
        assert mf.find_unclaimed(_descriptor()) is None
        # Owner still matches via is_available_for when id given.
        assert mf.find_unclaimed(_descriptor(), character_id="player") is e

    def test_reserved_only_matches_owner(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        e = _entry(mf)
        e.reserved_for = "tm_jordan"
        assert mf.find_unclaimed(_descriptor()) is None
        assert (
            mf.find_unclaimed(_descriptor(), character_id="tm_jordan") is e
        )


class TestManifestClaim:
    def test_claim_and_release(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        e = _entry(mf)
        mf.claim(e.entry_id, "player")
        assert e.claimed_by == "player"
        mf.release(e.entry_id)
        assert e.claimed_by is None

    def test_double_claim_rejected(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        e = _entry(mf)
        mf.claim(e.entry_id, "player")
        with pytest.raises(RuntimeError):
            mf.claim(e.entry_id, "someone_else")

    def test_claim_unknown_raises(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        with pytest.raises(KeyError):
            mf.claim("not_an_id", "player")

    def test_unclaimed_count(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        e1 = _entry(mf)
        e2 = _entry(mf)
        assert mf.unclaimed_count(_descriptor()) == 2
        mf.claim(e1.entry_id, "player")
        assert mf.unclaimed_count(_descriptor()) == 1


class TestManifestPersistence:
    def test_round_trip_to_disk(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        e = _entry(mf)
        e.variants["warm"] = f"{e.descriptor.bucket_key()}/{e.entry_id}/warm.png"
        mf.claim(e.entry_id, "player")
        mf.save()

        reloaded = SpriteManifest.load(tmp_path)
        assert len(reloaded.entries) == 1
        got = reloaded.entries[0]
        assert got.entry_id == e.entry_id
        assert got.descriptor == e.descriptor
        assert got.variants == e.variants
        assert got.claimed_by == "player"

    def test_load_missing_file_returns_empty(self, tmp_path: Path):
        mf = SpriteManifest.load(tmp_path)
        assert mf.entries == []

    def test_resolve_paths_under_assets_root(self, tmp_path: Path):
        mf = SpriteManifest(assets_root=tmp_path)
        e = _entry(mf)
        resolved = mf.resolve(e.neutral_path)
        assert resolved.is_relative_to(tmp_path)
