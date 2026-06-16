"""Tests for the background pool data layer (engine.background_pool)."""

from pathlib import Path

import pytest

from engine.background_pool import (
    BackgroundEntry,
    BackgroundManifest,
    Era,
    LocationDescriptor,
    LocationKind,
    MoodTone,
    SceneGraphInstance,
    SceneGraphSpec,
    Socioeconomic,
)


def _descriptor(**overrides) -> LocationDescriptor:
    base = dict(
        kind=LocationKind.SUBURBAN_HOUSE,
        era=Era.MODERN,
        socioeconomic=Socioeconomic.COMFORTABLE,
        mood=MoodTone.NEUTRAL,
    )
    base.update(overrides)
    return LocationDescriptor(**base)


def _spec(spec_id: str = "house") -> SceneGraphSpec:
    return SceneGraphSpec(
        spec_id=spec_id,
        kind=LocationKind.SUBURBAN_HOUSE,
        nodes=("front_door", "living_room", "kitchen", "hallway", "bathroom"),
        adjacency=(
            ("front_door", "living_room"),
            ("living_room", "kitchen"),
            ("living_room", "hallway"),
            ("hallway", "bathroom"),
        ),
        entry_nodes=("front_door",),
    )


def _entry(
    manifest: BackgroundManifest,
    descriptor: LocationDescriptor,
    spec_id: str,
    node_name: str,
    seed: int = 0,
) -> BackgroundEntry:
    entry_id = manifest.next_entry_id(descriptor, node_name)
    return BackgroundEntry(
        entry_id=entry_id,
        descriptor=descriptor,
        spec_id=spec_id,
        node_name=node_name,
        image_paths=[f"{descriptor.bucket_key()}/{spec_id}/{node_name}.png"],
        seed=seed,
    )


# --- Descriptor -------------------------------------------------------------


class TestDescriptor:
    def test_bucket_key_stable(self):
        assert _descriptor().bucket_key() == _descriptor().bucket_key()

    def test_bucket_key_changes_per_axis(self):
        baseline = _descriptor().bucket_key()
        assert _descriptor(kind=LocationKind.APARTMENT).bucket_key() != baseline
        assert _descriptor(era=Era.RETRO_90S).bucket_key() != baseline
        assert (
            _descriptor(socioeconomic=Socioeconomic.AFFLUENT).bucket_key()
            != baseline
        )
        assert _descriptor(mood=MoodTone.COLD).bucket_key() != baseline

    def test_palette_and_details_participate_via_hash(self):
        baseline = _descriptor().bucket_key()
        assert _descriptor(palette="warm oak").bucket_key() != baseline
        assert _descriptor(appearance_details="creaky").bucket_key() != baseline
        # Empty stays equal.
        assert _descriptor(palette="", appearance_details="").bucket_key() == baseline

    def test_prompt_fragment_mentions_axes(self):
        frag = _descriptor(
            kind=LocationKind.APARTMENT,
            era=Era.RETRO_90S,
            socioeconomic=Socioeconomic.MODEST,
            mood=MoodTone.WARM,
        ).to_prompt_fragment()
        assert "apartment" in frag
        assert "1990s" in frag
        assert "modest" in frag
        assert "warm" in frag

    def test_round_trip(self):
        d = _descriptor(palette="oak", appearance_details="floral wallpaper")
        assert LocationDescriptor.from_dict(d.to_dict()) == d


# --- SceneGraphSpec ---------------------------------------------------------


class TestSceneGraphSpec:
    def test_neighbors_undirected(self):
        s = _spec()
        assert "living_room" in s.neighbors("front_door")
        assert "front_door" in s.neighbors("living_room")
        assert set(s.neighbors("living_room")) >= {"front_door", "kitchen", "hallway"}

    def test_neighbors_unknown_node_raises(self):
        s = _spec()
        with pytest.raises(KeyError):
            s.neighbors("attic")

    def test_invalid_adjacency_rejected(self):
        with pytest.raises(ValueError):
            SceneGraphSpec(
                spec_id="bad",
                kind=LocationKind.SUBURBAN_HOUSE,
                nodes=("a",),
                adjacency=(("a", "ghost"),),
            )

    def test_invalid_entry_node_rejected(self):
        with pytest.raises(ValueError):
            SceneGraphSpec(
                spec_id="bad",
                kind=LocationKind.SUBURBAN_HOUSE,
                nodes=("a",),
                entry_nodes=("ghost",),
            )

    def test_empty_nodes_rejected(self):
        with pytest.raises(ValueError):
            SceneGraphSpec(
                spec_id="empty",
                kind=LocationKind.SUBURBAN_HOUSE,
                nodes=(),
            )


# --- Manifest CRUD ---------------------------------------------------------


class TestManifestBasics:
    def test_create_graph_assigns_id_when_omitted(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        g = mf.create_graph("house", _descriptor())
        assert g.graph_id.startswith("house_")
        assert mf.get_graph(g.graph_id) is g

    def test_create_graph_with_authored_id(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        g = mf.create_graph("house", _descriptor(), graph_id="player_home")
        assert g.graph_id == "player_home"

    def test_duplicate_graph_id_rejected(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="player_home")
        with pytest.raises(ValueError):
            mf.create_graph("house", _descriptor(), graph_id="player_home")

    def test_attach_entry_binds_to_slot(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        g = mf.create_graph("house", _descriptor(), graph_id="g1")
        e = _entry(mf, _descriptor(), "house", "front_door")
        mf.attach_entry(g.graph_id, "front_door", e)
        assert e.graph_id == "g1"
        assert g.node_entries["front_door"] == e.entry_id
        assert mf.get_attached("g1", "front_door") is e

    def test_attach_to_unknown_graph_raises(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        e = _entry(mf, _descriptor(), "house", "front_door")
        with pytest.raises(KeyError):
            mf.attach_entry("nope", "front_door", e)

    def test_attach_duplicate_node_rejected(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        e1 = _entry(mf, _descriptor(), "house", "front_door")
        mf.attach_entry("g1", "front_door", e1)
        e2 = _entry(mf, _descriptor(), "house", "front_door")
        with pytest.raises(RuntimeError):
            mf.attach_entry("g1", "front_door", e2)


# --- Visit + release -------------------------------------------------------


class TestVisitAndRelease:
    def test_mark_visited_sets_flag(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        e = _entry(mf, _descriptor(), "house", "front_door")
        mf.attach_entry("g1", "front_door", e)
        assert e.visited is False
        mf.mark_visited("g1", "front_door")
        assert e.visited is True

    def test_mark_visited_increments_count(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        e = _entry(mf, _descriptor(), "house", "front_door")
        mf.attach_entry("g1", "front_door", e)
        for expected in (1, 2, 3):
            mf.mark_visited("g1", "front_door")
            assert mf.get_graph("g1").visit_counts["front_door"] == expected

    def test_mark_visited_unknown_node_raises(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        with pytest.raises(KeyError):
            mf.mark_visited("g1", "front_door")

    def test_release_detaches_unvisited_keeps_visited(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        e_visited = _entry(mf, _descriptor(), "house", "front_door")
        e_pref = _entry(mf, _descriptor(), "house", "living_room")
        mf.attach_entry("g1", "front_door", e_visited)
        mf.attach_entry("g1", "living_room", e_pref)
        mf.mark_visited("g1", "front_door")  # only this one visited

        released = mf.release_graph("g1")
        assert [e.entry_id for e in released] == [e_pref.entry_id]
        assert e_pref.graph_id is None
        assert e_visited.graph_id == "g1"
        # Closed graph keeps only visited slots.
        g = mf.get_graph("g1")
        assert "front_door" in g.node_entries
        assert "living_room" not in g.node_entries
        assert g.closed is True

    def test_release_idempotent(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        assert mf.release_graph("g1") == []
        assert mf.release_graph("g1") == []  # closed → no-op

    def test_attach_to_closed_graph_rejected(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        mf.release_graph("g1")
        e = _entry(mf, _descriptor(), "house", "front_door")
        with pytest.raises(RuntimeError):
            mf.attach_entry("g1", "front_door", e)


# --- Adoption pool ---------------------------------------------------------


class TestAdoption:
    def test_pool_lookup_matches_descriptor_and_node(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        # Generate, attach, release without visit → ends up in pool.
        mf.create_graph("house", _descriptor(), graph_id="g1")
        e = _entry(mf, _descriptor(), "house", "kitchen")
        mf.attach_entry("g1", "kitchen", e)
        mf.release_graph("g1")
        assert e.graph_id is None
        assert mf.find_adoptable(_descriptor(), "kitchen") is e

    def test_pool_lookup_misses_when_node_differs(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        e = _entry(mf, _descriptor(), "house", "kitchen")
        mf.attach_entry("g1", "kitchen", e)
        mf.release_graph("g1")
        assert mf.find_adoptable(_descriptor(), "bathroom") is None

    def test_pool_lookup_misses_when_descriptor_differs(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        e = _entry(mf, _descriptor(), "house", "kitchen")
        mf.attach_entry("g1", "kitchen", e)
        mf.release_graph("g1")
        assert mf.find_adoptable(_descriptor(mood=MoodTone.COLD), "kitchen") is None

    def test_adopt_binds_pool_entry_to_cold_graph(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="old")
        e = _entry(mf, _descriptor(), "house", "kitchen")
        mf.attach_entry("old", "kitchen", e)
        mf.release_graph("old")

        mf.create_graph("house", _descriptor(), graph_id="new")
        adopted = mf.adopt("new", e.entry_id)
        assert adopted is e
        assert e.graph_id == "new"
        assert mf.get_graph("new").node_entries["kitchen"] == e.entry_id

    def test_adopt_rejected_when_graph_has_anchors(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="old")
        pool_e = _entry(mf, _descriptor(), "house", "kitchen")
        mf.attach_entry("old", "kitchen", pool_e)
        mf.release_graph("old")

        mf.create_graph("house", _descriptor(), graph_id="new")
        warm_e = _entry(mf, _descriptor(), "house", "front_door")
        mf.attach_entry("new", "front_door", warm_e)

        with pytest.raises(RuntimeError):
            mf.adopt("new", pool_e.entry_id)

    def test_pool_drains_fifo(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        for i in range(2):
            gid = f"g{i}"
            mf.create_graph("house", _descriptor(), graph_id=gid)
            e = _entry(mf, _descriptor(), "house", "kitchen")
            mf.attach_entry(gid, "kitchen", e)
            mf.release_graph(gid)
        # Two pool entries with the same key; first attached comes first.
        first = mf.pool_entries()[0]
        assert mf.find_adoptable(_descriptor(), "kitchen") is first


# --- Persistence -----------------------------------------------------------


class TestPersistence:
    def test_round_trip_to_disk(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        e = _entry(mf, _descriptor(), "house", "front_door")
        # Multi-variant entry: primary + one motion variant.
        e.image_paths.append(
            f"{e.descriptor.bucket_key()}/house/front_door_v1.png"
        )
        mf.attach_entry("g1", "front_door", e)
        mf.mark_visited("g1", "front_door")
        mf.mark_visited("g1", "front_door")
        mf.save()

        reloaded = BackgroundManifest.load(tmp_path)
        assert len(reloaded.entries) == 1
        assert len(reloaded.graphs) == 1
        got_e = reloaded.entries[0]
        got_g = reloaded.graphs[0]
        assert got_e.entry_id == e.entry_id
        assert got_e.graph_id == "g1"
        assert got_e.visited is True
        assert got_e.image_paths == e.image_paths
        assert got_g.node_entries == {"front_door": e.entry_id}
        assert got_g.visit_counts == {"front_door": 2}

    def test_round_trip_accepts_legacy_image_path(self, tmp_path: Path):
        """Older manifests on disk used `image_path` (single string).
        New code reloads them as single-variant entries."""
        import json

        mf = BackgroundManifest(assets_root=tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        legacy = {
            "version": 1,
            "entries": [
                {
                    "entry_id": "legacy_0",
                    "descriptor": _descriptor().to_dict(),
                    "spec_id": "house",
                    "node_name": "front_door",
                    "image_path": "x/front_door.png",
                    "seed": 42,
                    "graph_id": "g1",
                    "visited": True,
                }
            ],
            "graphs": [
                {
                    "graph_id": "g1",
                    "spec_id": "house",
                    "descriptor": _descriptor().to_dict(),
                    "node_entries": {"front_door": "legacy_0"},
                }
            ],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(legacy))
        reloaded = BackgroundManifest.load(tmp_path)
        assert reloaded.entries[0].image_paths == ["x/front_door.png"]
        assert reloaded.entries[0].primary_path == "x/front_door.png"

    def test_load_missing_returns_empty(self, tmp_path: Path):
        mf = BackgroundManifest.load(tmp_path)
        assert mf.entries == []
        assert mf.graphs == []


# --- Authored content sanity ----------------------------------------------


class TestAuthoredSpecs:
    def test_authored_specs_load(self):
        from engine.content_loader import load_scene_specs_from_path

        content_root = Path(__file__).resolve().parents[1] / "game" / "content"
        specs = load_scene_specs_from_path(content_root / "scenes")
        ids = {s.spec_id for s in specs}
        assert "suburban_house" in ids
        assert "school" in ids
        # Adjacency on the authored house spec is connected.
        house = next(s for s in specs if s.spec_id == "suburban_house")
        assert "living_room" in house.neighbors("front_door")

    def test_hot_tier_specs_authored(self):
        from engine.content_loader import load_scene_specs_from_path

        content_root = Path(__file__).resolve().parents[1] / "game" / "content"
        specs = {
            s.spec_id: s
            for s in load_scene_specs_from_path(content_root / "scenes")
        }
        for sid in ("apartment", "team_hq", "training_ground", "pitch", "cafe"):
            assert sid in specs, f"missing hot-tier spec {sid}"
        # Hottest scenes carry extra alternates.
        assert specs["team_hq"].alternate_count("locker_room") == 3
        assert specs["suburban_house"].alternate_count("kitchen") == 3
        assert specs["apartment"].alternate_count("bedroom") == 3
        # Cooler HQ rooms get the floor of 2.
        assert specs["team_hq"].alternate_count("showers") == 2

    def test_every_authored_node_has_a_prompt_hint(self):
        """The pre-bake driver builds prompts from these hints; a missing
        one would silently fall back to the bare node name."""
        from engine.background_generator import _NODE_PROMPT_HINTS
        from engine.content_loader import load_scene_specs_from_path

        content_root = Path(__file__).resolve().parents[1] / "game" / "content"
        specs = load_scene_specs_from_path(content_root / "scenes")
        missing = [
            f"{s.spec_id}/{n}"
            for s in specs
            for n in s.nodes
            if n not in _NODE_PROMPT_HINTS
        ]
        assert missing == [], f"nodes without prompt hints: {missing}"


# --- Alternates (Phase 23) -------------------------------------------------


class TestAlternates:
    def test_spec_alternate_count_default_and_declared(self):
        spec = SceneGraphSpec(
            spec_id="h",
            kind=LocationKind.SUBURBAN_HOUSE,
            nodes=("kitchen", "bathroom"),
            alternates=(("kitchen", 3),),
        )
        assert spec.alternate_count("kitchen") == 3
        assert spec.alternate_count("bathroom") == 1  # default

    def test_spec_rejects_unknown_alternate_node(self):
        with pytest.raises(ValueError):
            SceneGraphSpec(
                spec_id="h",
                kind=LocationKind.SUBURBAN_HOUSE,
                nodes=("kitchen",),
                alternates=(("garage", 2),),
            )

    def test_spec_rejects_zero_alternate_count(self):
        with pytest.raises(ValueError):
            SceneGraphSpec(
                spec_id="h",
                kind=LocationKind.SUBURBAN_HOUSE,
                nodes=("kitchen",),
                alternates=(("kitchen", 0),),
            )

    def _alt_entry(self, mf, desc, spec_id, node, n):
        e = BackgroundEntry(
            entry_id=f"{node}_alt{n}",
            descriptor=desc,
            spec_id=spec_id,
            node_name=node,
            image_paths=[f"x/{spec_id}/{node}_{n}.png"],
            seed=n,
        )
        return e

    def test_attach_and_get_alternates_in_order(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        desc = _descriptor()
        mf.create_graph("house", desc, graph_id="g1")
        for n in range(3):
            mf.attach_alternate("g1", "kitchen", self._alt_entry(mf, desc, "house", "kitchen", n))
        alts = mf.get_alternates("g1", "kitchen")
        assert [a.entry_id for a in alts] == ["kitchen_alt0", "kitchen_alt1", "kitchen_alt2"]
        # First alternate is also the primary binding.
        assert mf.get_attached("g1", "kitchen").entry_id == "kitchen_alt0"

    def test_attach_alternate_idempotent_on_same_id(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        desc = _descriptor()
        mf.create_graph("house", desc, graph_id="g1")
        e = self._alt_entry(mf, desc, "house", "kitchen", 0)
        mf.attach_alternate("g1", "kitchen", e)
        mf.attach_alternate("g1", "kitchen", e)
        assert len(mf.get_alternates("g1", "kitchen")) == 1

    def test_choose_alternate_rotates_by_visit(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        desc = _descriptor()
        mf.create_graph("house", desc, graph_id="g1")
        for n in range(3):
            mf.attach_alternate("g1", "kitchen", self._alt_entry(mf, desc, "house", "kitchen", n))
        picks = [mf.choose_alternate("g1", "kitchen", v).entry_id for v in range(7)]
        assert picks == [
            "kitchen_alt0", "kitchen_alt1", "kitchen_alt2",
            "kitchen_alt0", "kitchen_alt1", "kitchen_alt2", "kitchen_alt0",
        ]

    def test_get_alternates_falls_back_to_single_entry(self, tmp_path: Path):
        """On-demand graphs never populate node_alternates."""
        mf = BackgroundManifest(assets_root=tmp_path)
        desc = _descriptor()
        mf.create_graph("house", desc, graph_id="g1")
        mf.attach_entry("g1", "kitchen", _entry(mf, desc, "house", "kitchen"))
        alts = mf.get_alternates("g1", "kitchen")
        assert len(alts) == 1
        assert mf.choose_alternate("g1", "kitchen", 5) is alts[0]

    def test_node_alternates_survive_save_round_trip(self, tmp_path: Path):
        mf = BackgroundManifest(assets_root=tmp_path)
        desc = _descriptor()
        mf.create_graph("house", desc, graph_id="g1")
        for n in range(2):
            mf.attach_alternate("g1", "kitchen", self._alt_entry(mf, desc, "house", "kitchen", n))
        mf.save()
        reloaded = BackgroundManifest.load(tmp_path)
        assert [a.entry_id for a in reloaded.get_alternates("g1", "kitchen")] == [
            "kitchen_alt0", "kitchen_alt1",
        ]
