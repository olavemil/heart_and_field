"""Tests for the background generator orchestration."""

from pathlib import Path

import pytest

from engine.background_generator import (
    BackgroundGenerationError,
    BackgroundGenerator,
    DeferredPrefetchScheduler,
    InlinePrefetchScheduler,
    MAX_VARIANTS_PER_NODE,
    NoOpPrefetchScheduler,
    PlaceholderImageProducer,
)
from engine.background_pool import (
    BackgroundManifest,
    Era,
    LocationDescriptor,
    LocationKind,
    MoodTone,
    SceneGraphSpec,
    Socioeconomic,
)


# --- Helpers ---------------------------------------------------------------


def _descriptor(**overrides) -> LocationDescriptor:
    base = dict(
        kind=LocationKind.SUBURBAN_HOUSE,
        era=Era.MODERN,
        socioeconomic=Socioeconomic.COMFORTABLE,
        mood=MoodTone.NEUTRAL,
    )
    base.update(overrides)
    return LocationDescriptor(**base)


def _spec() -> SceneGraphSpec:
    return SceneGraphSpec(
        spec_id="house",
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


class RecordingProducer:
    """Trivial producer: writes a marker file and records every call."""

    def __init__(self):
        self.calls: list[dict] = []

    def produce(
        self,
        *,
        descriptor,
        spec,
        node_name,
        seed,
        anchor_path,
        out_path,
        variant_index=0,
    ) -> None:
        self.calls.append(
            {
                "node_name": node_name,
                "seed": seed,
                "anchor_path": anchor_path,
                "out_path": out_path,
                "variant_index": variant_index,
            }
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(
            b"\x89PNG\r\n\x1a\n" + f"{node_name}_v{variant_index}".encode()
        )


def _gen(
    tmp_path: Path,
    *,
    scheduler=None,
    producer=None,
) -> tuple[BackgroundGenerator, BackgroundManifest, RecordingProducer]:
    mf = BackgroundManifest(assets_root=tmp_path)
    p = producer or RecordingProducer()
    gen = BackgroundGenerator(
        manifest=mf,
        specs={"house": _spec()},
        producer=p,
        prefetch_scheduler=scheduler or NoOpPrefetchScheduler(),
    )
    return gen, mf, p


# --- Hot path --------------------------------------------------------------


class TestGetBackground:
    def test_first_call_generates_and_marks_visited(self, tmp_path: Path):
        gen, mf, producer = _gen(tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")

        path = gen.get_background("g1", "front_door")

        assert path.exists()
        assert len(producer.calls) == 1
        assert producer.calls[0]["anchor_path"] is None  # first node — no anchor
        entry = mf.get_attached("g1", "front_door")
        assert entry is not None
        assert entry.visited is True
        assert entry.anchor_entry_id is None

    def test_second_call_reuses_attached_entry(self, tmp_path: Path):
        gen, mf, producer = _gen(tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        gen.get_background("g1", "front_door")
        gen.get_background("g1", "front_door")
        assert len(producer.calls) == 1  # not regenerated

    def test_subsequent_node_uses_anchor_from_sibling(self, tmp_path: Path):
        gen, mf, producer = _gen(tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        gen.get_background("g1", "front_door")
        gen.get_background("g1", "living_room")
        assert len(producer.calls) == 2
        assert producer.calls[1]["anchor_path"] is not None
        assert producer.calls[1]["anchor_path"].name == "front_door.png"

        living = mf.get_attached("g1", "living_room")
        assert living.anchor_entry_id is not None

    def test_unknown_graph_raises(self, tmp_path: Path):
        gen, _, _ = _gen(tmp_path)
        with pytest.raises(KeyError):
            gen.get_background("nope", "front_door")

    def test_unknown_node_raises(self, tmp_path: Path):
        gen, mf, _ = _gen(tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        with pytest.raises(KeyError):
            gen.get_background("g1", "attic")

    def test_producer_failure_surfaces(self, tmp_path: Path):
        class Broken:
            def produce(self, **kw):
                raise OSError("disk full")

        gen, mf, _ = _gen(tmp_path, producer=Broken())
        mf.create_graph("house", _descriptor(), graph_id="g1")
        with pytest.raises(BackgroundGenerationError):
            gen.get_background("g1", "front_door")

    def test_seed_is_deterministic_per_graph_and_node(self, tmp_path: Path):
        gen, mf, producer = _gen(tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        mf.create_graph("house", _descriptor(), graph_id="g2")

        gen.get_background("g1", "front_door")
        gen.get_background("g2", "front_door")
        seeds = [c["seed"] for c in producer.calls]
        # Same descriptor, same node, but different graph_ids → different seeds.
        assert seeds[0] != seeds[1]
        # Re-creating the same graph_id wouldn't be allowed, but the formula
        # should be reproducible for the same inputs.


# --- Prefetch --------------------------------------------------------------


class TestPrefetch:
    def test_inline_scheduler_generates_neighbors_immediately(self, tmp_path: Path):
        gen, mf, producer = _gen(tmp_path, scheduler=InlinePrefetchScheduler())
        mf.create_graph("house", _descriptor(), graph_id="g1")

        gen.get_background("g1", "front_door")

        # front_door (visited) + living_room (prefetched neighbor).
        attached_nodes = {
            n
            for n, eid in mf.get_graph("g1").node_entries.items()
        }
        assert "front_door" in attached_nodes
        assert "living_room" in attached_nodes

        prefetched = mf.get_attached("g1", "living_room")
        assert prefetched is not None
        assert prefetched.visited is False  # prefetch never visits

    def test_deferred_scheduler_queues_neighbors(self, tmp_path: Path):
        sched = DeferredPrefetchScheduler()
        gen, mf, producer = _gen(tmp_path, scheduler=sched)
        mf.create_graph("house", _descriptor(), graph_id="g1")

        gen.get_background("g1", "front_door")
        # Hot path generated only the requested node.
        assert len(producer.calls) == 1
        assert sched.pending() == 1  # one neighbor (living_room)

        sched.drain()
        # Now living_room is generated.
        assert len(producer.calls) == 2
        assert mf.get_attached("g1", "living_room") is not None

    def test_noop_scheduler_skips_prefetch(self, tmp_path: Path):
        gen, mf, producer = _gen(tmp_path, scheduler=NoOpPrefetchScheduler())
        mf.create_graph("house", _descriptor(), graph_id="g1")

        gen.get_background("g1", "front_door")
        assert len(producer.calls) == 1
        assert mf.get_attached("g1", "living_room") is None

    def test_prefetch_skips_already_attached(self, tmp_path: Path):
        sched = DeferredPrefetchScheduler()
        gen, mf, producer = _gen(tmp_path, scheduler=sched)
        mf.create_graph("house", _descriptor(), graph_id="g1")

        gen.get_background("g1", "front_door")
        gen.get_background("g1", "living_room")
        # Both visited; pending queue may have stale neighbors but draining
        # them must not regenerate or duplicate anything.
        before = len(producer.calls)
        sched.drain()
        for n, eid in mf.get_graph("g1").node_entries.items():
            assert eid is not None
        # Some draining may produce kitchen/hallway, that's fine — the
        # important property is no duplicate attach for visited nodes.
        attached = mf.get_graph("g1").node_entries
        assert len(attached) == len(set(attached.values()))


# --- Adoption integration --------------------------------------------------


class TestAdoptionIntegration:
    def test_cold_start_graph_adopts_pool_entry(self, tmp_path: Path):
        gen, mf, producer = _gen(tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="old")
        gen.get_background("old", "kitchen")  # generates + visits
        # Detach unvisited (none in this case) and visited stays...
        # We need an unvisited entry. Use prefetch to create one then release.
        sched = DeferredPrefetchScheduler()
        gen2_mf = mf  # reuse same manifest
        gen2 = BackgroundGenerator(
            manifest=gen2_mf,
            specs={"house": _spec()},
            producer=producer,
            prefetch_scheduler=sched,
        )
        gen2.prefetch_node("old", "living_room")  # not visited
        mf.release_graph("old")

        # living_room is in the pool; create a fresh graph and adopt.
        mf.create_graph("house", _descriptor(), graph_id="new")
        before_calls = len(producer.calls)
        path = gen.get_background("new", "living_room")
        # Adoption used the pool entry — no new produce call.
        assert len(producer.calls) == before_calls
        assert path.exists()
        adopted = mf.get_attached("new", "living_room")
        assert adopted is not None
        assert adopted.graph_id == "new"

    def test_warm_graph_does_not_adopt(self, tmp_path: Path):
        gen, mf, producer = _gen(tmp_path)
        # Prime the pool with an unvisited kitchen.
        mf.create_graph("house", _descriptor(), graph_id="seed")
        gen.prefetch_node("seed", "kitchen")
        mf.release_graph("seed")
        assert mf.find_adoptable(_descriptor(), "kitchen") is not None

        # New graph: generate front_door (anchor) first, then ask for kitchen.
        mf.create_graph("house", _descriptor(), graph_id="new")
        gen.get_background("new", "front_door")
        before = len(producer.calls)
        gen.get_background("new", "kitchen")
        # Produced fresh, did not adopt — anchors would mismatch otherwise.
        assert len(producer.calls) == before + 1
        assert mf.find_adoptable(_descriptor(), "kitchen") is not None  # pool intact


# --- Placeholder producer --------------------------------------------------


class TestVariants:
    def test_first_visit_yields_primary_only(self, tmp_path: Path):
        gen, mf, _ = _gen(tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        gen.get_background("g1", "front_door")
        entry = mf.get_attached("g1", "front_door")
        assert len(entry.image_paths) == 1

    def test_second_visit_schedules_second_variant(self, tmp_path: Path):
        sched = DeferredPrefetchScheduler()
        gen, mf, producer = _gen(tmp_path, scheduler=sched)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        gen.get_background("g1", "front_door")
        sched.drain()  # clear neighbor prefetch
        before = len(producer.calls)

        gen.get_background("g1", "front_door")
        # Visit count is now 2; one variant job pending.
        assert sched.pending() >= 1
        sched.drain()
        entry = mf.get_attached("g1", "front_door")
        assert len(entry.image_paths) == 2
        # The variant produce call carried variant_index=1 and an anchor.
        variant_call = producer.calls[before]
        assert variant_call["variant_index"] == 1
        assert variant_call["anchor_path"] is not None

    def test_third_visit_schedules_third_variant(self, tmp_path: Path):
        sched = DeferredPrefetchScheduler()
        gen, mf, _ = _gen(tmp_path, scheduler=sched)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        for _ in range(3):
            gen.get_background("g1", "front_door")
        sched.drain()
        entry = mf.get_attached("g1", "front_door")
        assert len(entry.image_paths) == MAX_VARIANTS_PER_NODE

    def test_visits_beyond_cap_do_not_grow_variants(self, tmp_path: Path):
        sched = DeferredPrefetchScheduler()
        gen, mf, producer = _gen(tmp_path, scheduler=sched)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        for _ in range(MAX_VARIANTS_PER_NODE + 3):
            gen.get_background("g1", "front_door")
        sched.drain()
        entry = mf.get_attached("g1", "front_door")
        assert len(entry.image_paths) == MAX_VARIANTS_PER_NODE

    def test_generate_variant_no_op_without_primary(self, tmp_path: Path):
        gen, mf, _ = _gen(tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        # No call to get_background: nothing attached.
        result = gen.generate_variant("g1", "front_door")
        assert result is None

    def test_generate_variant_uses_primary_as_anchor(self, tmp_path: Path):
        gen, mf, producer = _gen(tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        gen.get_background("g1", "front_door")  # primary
        gen.get_background("g1", "living_room")  # second node, different sibling

        before = len(producer.calls)
        gen.generate_variant("g1", "living_room")
        # Anchor is the living_room primary, not the front_door primary —
        # variants always anchor on their own node's primary.
        anchor = producer.calls[before]["anchor_path"]
        assert anchor.name == "living_room.png"

    def test_warm_node_schedules_primary_and_variants(self, tmp_path: Path):
        sched = DeferredPrefetchScheduler()
        gen, mf, producer = _gen(tmp_path, scheduler=sched)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        gen.warm_node("g1", "front_door")
        # 1 primary + 2 variants = 3 jobs queued (cap = MAX_VARIANTS_PER_NODE).
        assert sched.pending() == MAX_VARIANTS_PER_NODE
        sched.drain()
        entry = mf.get_attached("g1", "front_door")
        assert len(entry.image_paths) == MAX_VARIANTS_PER_NODE

    def test_warm_node_after_primary_only_schedules_variants(self, tmp_path: Path):
        sched = DeferredPrefetchScheduler()
        gen, mf, _ = _gen(tmp_path, scheduler=sched)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        gen.get_background("g1", "front_door")
        sched.drain()  # primary done

        gen.warm_node("g1", "front_door")
        # Two variants left to reach the cap.
        assert sched.pending() == MAX_VARIANTS_PER_NODE - 1


class TestPlaceholderProducer:
    def test_writes_a_png(self, tmp_path: Path):
        producer = PlaceholderImageProducer(width=128, height=64)
        out = tmp_path / "x.png"
        producer.produce(
            descriptor=_descriptor(),
            spec=_spec(),
            node_name="front_door",
            seed=42,
            anchor_path=None,
            out_path=out,
        )
        assert out.exists()
        # PNG magic number.
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_variant_index_changes_pixels(self, tmp_path: Path):
        producer = PlaceholderImageProducer(width=64, height=64)
        primary = tmp_path / "primary.png"
        variant = tmp_path / "variant.png"
        producer.produce(
            descriptor=_descriptor(),
            spec=_spec(),
            node_name="front_door",
            seed=1,
            anchor_path=None,
            out_path=primary,
            variant_index=0,
        )
        producer.produce(
            descriptor=_descriptor(),
            spec=_spec(),
            node_name="front_door",
            seed=1,
            anchor_path=primary,
            out_path=variant,
            variant_index=1,
        )
        # Same node + descriptor + seed but different variant_index → distinct
        # pixels (placeholder shifts hue/value subtly per variant).
        assert primary.read_bytes() != variant.read_bytes()

    def test_distinct_buckets_yield_distinct_pixels(self, tmp_path: Path):
        producer = PlaceholderImageProducer(width=64, height=64)
        a = tmp_path / "a.png"
        b = tmp_path / "b.png"
        producer.produce(
            descriptor=_descriptor(mood=MoodTone.WARM),
            spec=_spec(),
            node_name="front_door",
            seed=1,
            anchor_path=None,
            out_path=a,
        )
        producer.produce(
            descriptor=_descriptor(mood=MoodTone.COLD),
            spec=_spec(),
            node_name="front_door",
            seed=1,
            anchor_path=None,
            out_path=b,
        )
        # Different bucket → different colour.
        assert a.read_bytes() != b.read_bytes()


# --- Alternate-aware serving + prebaked producer (Phase 23) ----------------


def _attach_alts(mf, gen, graph_id, node, n):
    """Pre-attach n distinct alternates (each with a couple of motion
    variants) to mimic a pre-baked graph."""
    from engine.background_pool import BackgroundEntry

    desc = _descriptor()
    for a in range(n):
        e = BackgroundEntry(
            entry_id=f"{node}_alt{a}",
            descriptor=desc,
            spec_id="house",
            node_name=node,
            image_paths=[
                f"x/{node}_{a}_primary.png",
                f"x/{node}_{a}_motion1.png",
            ],
            seed=a,
        )
        mf.attach_alternate(graph_id, node, e)


class TestAlternateServing:
    def test_revisits_rotate_alternates(self, tmp_path: Path):
        gen, mf, _ = _gen(tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        _attach_alts(mf, gen, "g1", "kitchen", 3)
        served = [gen.get_background("g1", "kitchen").name for _ in range(4)]
        assert served == [
            "kitchen_0_primary.png",
            "kitchen_1_primary.png",
            "kitchen_2_primary.png",
            "kitchen_0_primary.png",  # wraps
        ]

    def test_variants_match_served_alternate(self, tmp_path: Path):
        """The crossfade set must belong to the shot just served."""
        gen, mf, _ = _gen(tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        _attach_alts(mf, gen, "g1", "kitchen", 3)
        # First serve → alt0; its variants must be alt0's, not alt1's.
        primary = gen.get_background("g1", "kitchen")
        variants = gen.get_variants("g1", "kitchen")
        assert primary.name == "kitchen_0_primary.png"
        assert [v.name for v in variants] == [
            "kitchen_0_primary.png",
            "kitchen_0_motion1.png",
        ]
        # Second serve → alt1; variants follow.
        gen.get_background("g1", "kitchen")
        assert [v.name for v in gen.get_variants("g1", "kitchen")] == [
            "kitchen_1_primary.png",
            "kitchen_1_motion1.png",
        ]

    def test_single_alternate_path_unchanged(self, tmp_path: Path):
        """On-demand (no alternates) still generates + serves one shot."""
        gen, mf, producer = _gen(tmp_path)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        p1 = gen.get_background("g1", "front_door")
        p2 = gen.get_background("g1", "front_door")
        assert p1 == p2  # same single entry every visit
        assert len(producer.calls) == 1  # generated once


class TestPrebakedProducer:
    def test_strict_raises_on_missing(self, tmp_path: Path):
        from engine.background_generator import PrebakedImageProducer

        prod = PrebakedImageProducer(strict=True)
        gen, mf, _ = _gen(tmp_path, producer=prod)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        # No pre-attached entry → serving must materialise → producer
        # called → strict mode surfaces the packaging gap (wrapped by the
        # materialise path as BackgroundGenerationError).
        with pytest.raises(BackgroundGenerationError, match="pre-baked asset missing"):
            gen.get_background("g1", "front_door")

    def test_lenient_falls_back_to_placeholder(self, tmp_path: Path):
        from engine.background_generator import PrebakedImageProducer

        prod = PrebakedImageProducer(strict=False)
        gen, mf, _ = _gen(tmp_path, producer=prod)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        path = gen.get_background("g1", "front_door")
        assert path.exists()  # placeholder written, no crash

    def test_prebaked_serves_without_producing(self, tmp_path: Path):
        """With assets pre-attached, the producer is never touched."""
        from engine.background_generator import PrebakedImageProducer

        prod = PrebakedImageProducer(strict=True)  # would raise if called
        gen, mf, _ = _gen(tmp_path, producer=prod)
        mf.create_graph("house", _descriptor(), graph_id="g1")
        _attach_alts(mf, gen, "g1", "kitchen", 2)
        # Pre-baked: serving returns attached paths, no produce() call.
        assert gen.get_background("g1", "kitchen").name == "kitchen_0_primary.png"
