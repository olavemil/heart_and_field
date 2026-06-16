"""Tests for scripts/prebake_assets.py (Phase 23D).

Runs the driver in placeholder mode (no GPU) so the enumeration,
manifest writing, alternate attachment, and idempotency are covered by
the regression gate.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_driver():
    spec = importlib.util.spec_from_file_location(
        "_prebake_driver", ROOT / "scripts" / "prebake_assets.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(driver, argv, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["prebake_assets.py", *argv])
    return driver.main()


def test_seed_is_deterministic_and_distinct():
    driver = _load_driver()
    assert driver.seed_for("a", "b", 0) == driver.seed_for("a", "b", 0)
    assert driver.seed_for("a", "b", 0) != driver.seed_for("a", "b", 1)
    assert driver.seed_for("a", "b", 0) != driver.seed_for("a", "c", 0)


def test_placeholder_bake_populates_manifest(tmp_path, monkeypatch):
    from engine.background_pool import BackgroundManifest

    driver = _load_driver()
    rc = _run(driver, ["--placeholder", "--out", str(tmp_path)], monkeypatch)
    assert rc == 0

    mf = BackgroundManifest.load(tmp_path)
    # One graph per authored spec; locker_room carries its 3 alternates.
    hq = mf.get_graph("team_hq")
    assert hq is not None
    assert len(hq.node_alternates["locker_room"]) == 3
    # Every entry's image file exists on disk.
    for entry in mf.entries:
        assert (tmp_path / entry.primary_path).exists()


def test_rerun_is_idempotent(tmp_path, monkeypatch):
    from engine.background_pool import BackgroundManifest

    driver = _load_driver()
    _run(driver, ["--placeholder", "--out", str(tmp_path)], monkeypatch)
    n_png = len(list(tmp_path.rglob("*.png")))
    n_entries = len(BackgroundManifest.load(tmp_path).entries)

    # Second run must not duplicate files or entries.
    _run(driver, ["--placeholder", "--out", str(tmp_path)], monkeypatch)
    assert len(list(tmp_path.rglob("*.png"))) == n_png
    assert len(BackgroundManifest.load(tmp_path).entries) == n_entries


def test_only_restricts_to_one_spec(tmp_path, monkeypatch):
    from engine.background_pool import BackgroundManifest

    driver = _load_driver()
    rc = _run(
        driver,
        ["--placeholder", "--only", "cafe", "--out", str(tmp_path)],
        monkeypatch,
    )
    assert rc == 0
    mf = BackgroundManifest.load(tmp_path)
    assert [g.graph_id for g in mf.graphs] == ["cafe"]
    # cafe = coffee_shop + bakery, 3 alternates each = 6 shots.
    assert len(mf.entries) == 6
