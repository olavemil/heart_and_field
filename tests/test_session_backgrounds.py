"""Integration: GameSession ↔ background pipeline."""

from pathlib import Path

import pytest

from engine.background_generator import (
    DeferredPrefetchScheduler,
    NoOpPrefetchScheduler,
)
from engine.background_pool import (
    LocationDescriptor,
    LocationKind,
    MoodTone,
)
from engine.events import (
    BranchOutcome,
    EventBlueprint,
    LocationCue,
    RoleSlot,
    SceneBlock,
)
from engine.session import GameSession


def _build_session(tmp_path: Path, *, scheduler=None) -> GameSession:
    session = GameSession.new_game("Alex Morgan", seed=42)
    session.init_backgrounds(
        tmp_path / "bg",
        prefetch_scheduler=scheduler or NoOpPrefetchScheduler(),
    )
    return session


def _house_blueprint(graph_id: str | None = None, node: str = "front_door") -> EventBlueprint:
    return EventBlueprint(
        id=f"test.scene_event_{graph_id or 'adhoc'}",
        tags={"downtime"},
        participants=[RoleSlot(role="player")],
        blocks=[SceneBlock(id="main")],
        outcomes={"x": BranchOutcome(summary="Something happened.")},
        location=LocationCue(
            spec_id="suburban_house",
            node_name=node,
            graph_id=graph_id,
        ),
    )


# --- Init / scene specs ----------------------------------------------------


class TestInit:
    def test_new_game_loads_authored_specs(self, tmp_path: Path):
        s = _build_session(tmp_path)
        assert "suburban_house" in s.scene_specs
        assert "school" in s.scene_specs

    def test_init_backgrounds_creates_manifest(self, tmp_path: Path):
        s = _build_session(tmp_path)
        assert s.background_manifest is not None
        assert s.background_generator is not None

    def test_prebaked_mode_uses_readonly_producer_and_noop_scheduler(
        self, tmp_path: Path
    ):
        from engine.background_generator import (
            NoOpPrefetchScheduler,
            PrebakedImageProducer,
        )

        s = GameSession.new_game("Alex Morgan", seed=42)
        s.init_backgrounds(tmp_path / "bg", prebaked=True)
        gen = s.background_generator
        assert isinstance(gen.producer, PrebakedImageProducer)
        assert isinstance(gen.prefetch_scheduler, NoOpPrefetchScheduler)

    def test_prebaked_mode_skips_marquee_warmup(self, tmp_path: Path):
        # warm_marquees would create graphs; prebaked must no-op it so the
        # shipped pack's manifest is the single source of truth.
        s = GameSession.new_game("Alex Morgan", seed=42)
        s.init_backgrounds(tmp_path / "bg", prebaked=True, warm_marquees=True)
        assert s.background_manifest.graphs == []

    def test_resolve_returns_none_without_init(self, tmp_path: Path):
        s = GameSession.new_game("Alex Morgan", seed=1)
        bp = _house_blueprint(graph_id="player_home")
        assert s.resolve_scene(bp, {}) is None


# --- Marquee resolution ----------------------------------------------------


class TestMarquee:
    def test_resolve_creates_marquee_graph_first_time(self, tmp_path: Path):
        s = _build_session(tmp_path)
        bp = _house_blueprint(graph_id="player_home")
        result = s.resolve_scene(bp, {})
        assert result == ("player_home", "front_door")
        assert s.background_manifest.get_graph("player_home") is not None

    def test_resolve_reuses_marquee_graph(self, tmp_path: Path):
        s = _build_session(tmp_path)
        bp = _house_blueprint(graph_id="player_home")
        s.resolve_scene(bp, {})
        # Second call: graph still here, no duplicate.
        s.resolve_scene(bp, {})
        graphs = [g for g in s.background_manifest.graphs if g.graph_id == "player_home"]
        assert len(graphs) == 1

    def test_marquee_release_does_not_close(self, tmp_path: Path):
        s = _build_session(tmp_path)
        bp = _house_blueprint(graph_id="player_home")
        s.resolve_scene(bp, {})
        s.scene_path("player_home", "front_door")  # generates + visits
        s.release_scene("player_home", close=False)
        assert s.background_manifest.get_graph("player_home").closed is False


# --- Ad-hoc resolution -----------------------------------------------------


class TestAdHoc:
    def test_adhoc_creates_fresh_graph_each_call(self, tmp_path: Path):
        s = _build_session(tmp_path)
        bp = _house_blueprint(graph_id=None)
        a = s.resolve_scene(bp, {})
        b = s.resolve_scene(bp, {})
        assert a is not None and b is not None
        assert a[0] != b[0]
        assert a[1] == b[1] == "front_door"

    def test_adhoc_close_marks_graph_done(self, tmp_path: Path):
        s = _build_session(tmp_path)
        bp = _house_blueprint(graph_id=None)
        graph_id, _ = s.resolve_scene(bp, {})
        s.scene_path(graph_id, "front_door")
        s.release_scene(graph_id, close=True)
        assert s.background_manifest.get_graph(graph_id).closed is True

    def test_adhoc_descriptor_uses_default(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.set_default_descriptor(
            "suburban_house",
            LocationDescriptor(kind=LocationKind.SUBURBAN_HOUSE, mood=MoodTone.WARM),
        )
        bp = _house_blueprint(graph_id=None)
        graph_id, _ = s.resolve_scene(bp, {})
        graph = s.background_manifest.get_graph(graph_id)
        assert graph.descriptor.mood == MoodTone.WARM

    def test_adhoc_descriptor_overrides_merge(self, tmp_path: Path):
        s = _build_session(tmp_path)
        s.set_default_descriptor(
            "suburban_house",
            LocationDescriptor(kind=LocationKind.SUBURBAN_HOUSE, mood=MoodTone.WARM),
        )
        bp = EventBlueprint(
            id="test.cold_house",
            tags={"downtime"},
            participants=[RoleSlot(role="player")],
            blocks=[SceneBlock(id="main")],
            outcomes={"x": BranchOutcome(summary=".")},
            location=LocationCue(
                spec_id="suburban_house",
                node_name="kitchen",
                descriptor_overrides={"mood": "cold"},
            ),
        )
        graph_id, _ = s.resolve_scene(bp, {})
        graph = s.background_manifest.get_graph(graph_id)
        assert graph.descriptor.mood == MoodTone.COLD


# --- scene_path ------------------------------------------------------------


class TestScenePath:
    def test_returns_path_and_marks_visited(self, tmp_path: Path):
        s = _build_session(tmp_path)
        bp = _house_blueprint(graph_id="player_home")
        graph_id, node = s.resolve_scene(bp, {})
        path = s.scene_path(graph_id, node)
        assert path is not None
        assert path.exists()
        entry = s.background_manifest.get_attached(graph_id, node)
        assert entry.visited is True

    def test_returns_none_without_pipeline(self, tmp_path: Path):
        s = GameSession.new_game("Alex Morgan", seed=1)
        # No init_backgrounds called.
        assert s.scene_path("anything", "anywhere") is None


# --- Prefetch drain --------------------------------------------------------


class TestPrefetchDrain:
    def test_drain_runs_pending_jobs(self, tmp_path: Path):
        sched = DeferredPrefetchScheduler()
        s = _build_session(tmp_path, scheduler=sched)
        bp = _house_blueprint(graph_id="player_home")
        graph_id, node = s.resolve_scene(bp, {})
        s.scene_path(graph_id, node)
        # Hot-path generated only `front_door`; living_room is queued.
        assert sched.pending() >= 1
        ran = s.drain_background_prefetch()
        assert ran >= 1


# --- Pool flow end-to-end --------------------------------------------------


class TestVariantsAndWarmup:
    def test_scene_variants_returns_primary_only_after_first_visit(
        self, tmp_path: Path
    ):
        s = _build_session(tmp_path)
        bp = _house_blueprint(graph_id="player_home")
        graph_id, node = s.resolve_scene(bp, {})
        s.scene_path(graph_id, node)
        variants = s.scene_variants(graph_id, node)
        assert len(variants) == 1
        assert variants[0].exists()

    def test_scene_variants_grows_on_revisit(self, tmp_path: Path):
        sched = DeferredPrefetchScheduler()
        s = _build_session(tmp_path, scheduler=sched)
        bp = _house_blueprint(graph_id="player_home")
        graph_id, node = s.resolve_scene(bp, {})

        s.scene_path(graph_id, node)
        s.drain_background_prefetch()  # first visit → 1 variant
        assert len(s.scene_variants(graph_id, node)) == 1

        s.scene_path(graph_id, node)  # second visit
        s.drain_background_prefetch()
        assert len(s.scene_variants(graph_id, node)) == 2

        s.scene_path(graph_id, node)  # third visit
        s.drain_background_prefetch()
        assert len(s.scene_variants(graph_id, node)) == 3

        s.scene_path(graph_id, node)  # fourth visit — capped
        s.drain_background_prefetch()
        assert len(s.scene_variants(graph_id, node)) == 3

    def test_scene_variants_empty_when_pipeline_off(self, tmp_path: Path):
        s = GameSession.new_game("Alex Morgan", seed=1)
        assert s.scene_variants("anything", "anywhere") == []

    def test_warm_marquees_creates_graphs_for_authored_cues(
        self, tmp_path: Path
    ):
        sched = DeferredPrefetchScheduler()
        s = _build_session(tmp_path, scheduler=sched)
        warmed = s.warm_marquees()
        # Authored content tags `player_home` and `main_school` as marquees.
        assert warmed >= 2
        assert s.background_manifest.get_graph("player_home") is not None
        assert s.background_manifest.get_graph("main_school") is not None
        # Each marquee scheduled 3 jobs (primary + 2 variants).
        assert sched.pending() == warmed * 3

    def test_warm_marquees_idempotent(self, tmp_path: Path):
        sched = DeferredPrefetchScheduler()
        s = _build_session(tmp_path, scheduler=sched)
        first = s.warm_marquees()
        sched.drain()
        second = s.warm_marquees()
        # Second pass: graphs exist, primary attached → only schedules
        # variants if the primary completed; no new graph creations.
        assert second == first  # same number of marquees seen
        # Idempotent: running again with all variants warm queues nothing new.
        sched.drain()
        third = s.warm_marquees()
        assert third == first

    def test_init_backgrounds_warm_marquees_flag(self, tmp_path: Path):
        sched = DeferredPrefetchScheduler()
        s = GameSession.new_game("Alex Morgan", seed=42)
        s.init_backgrounds(
            tmp_path / "bg",
            prefetch_scheduler=sched,
            warm_marquees=True,
        )
        # Marquee graphs were eagerly created.
        assert s.background_manifest.get_graph("player_home") is not None
        assert s.background_manifest.get_graph("main_school") is not None


class TestPoolFlow:
    def test_unvisited_prefetch_flows_to_pool_after_release(self, tmp_path: Path):
        sched = DeferredPrefetchScheduler()
        s = _build_session(tmp_path, scheduler=sched)
        bp = _house_blueprint(graph_id=None, node="front_door")
        graph_id, node = s.resolve_scene(bp, {})
        s.scene_path(graph_id, node)
        s.drain_background_prefetch()  # generate prefetched neighbors

        s.release_scene(graph_id, close=True)
        # Unvisited prefetched entries should be in the adoption pool now.
        pool = s.background_manifest.pool_entries()
        assert len(pool) >= 1
        # Their graph_id has been cleared.
        assert all(e.graph_id is None for e in pool)


class TestPrebakedServing:
    def test_scene_path_and_variants_agree_on_alternate(self, tmp_path: Path):
        """The crux of Phase 23B: scene_path and scene_variants are
        separate Ren'Py calls and must reference the same alternate."""
        from engine.background_pool import BackgroundEntry

        s = GameSession.new_game("Alex Morgan", seed=42)
        s.init_backgrounds(tmp_path / "bg", prebaked=True)
        mf = s.background_manifest
        desc = s._descriptor_for(
            LocationCue(spec_id="suburban_house", node_name="kitchen", graph_id="ph")
        )
        mf.create_graph("suburban_house", desc, graph_id="ph")
        for a in range(2):
            mf.attach_alternate(
                "ph",
                "kitchen",
                BackgroundEntry(
                    entry_id=f"kitchen_alt{a}",
                    descriptor=desc,
                    spec_id="suburban_house",
                    node_name="kitchen",
                    image_paths=[f"k_{a}_p.png", f"k_{a}_m.png"],
                    seed=a,
                ),
            )

        # Visit 1 → alt0: primary and variants both alt0.
        p1 = s.scene_path("ph", "kitchen")
        v1 = s.scene_variants("ph", "kitchen")
        assert p1.name == "k_0_p.png"
        assert [v.name for v in v1] == ["k_0_p.png", "k_0_m.png"]

        # Visit 2 → alt1: both follow.
        p2 = s.scene_path("ph", "kitchen")
        v2 = s.scene_variants("ph", "kitchen")
        assert p2.name == "k_1_p.png"
        assert [v.name for v in v2] == ["k_1_p.png", "k_1_m.png"]


class TestPrebakedResolve:
    """Phase 23: prebaked cue -> canonical per-spec graph mapping."""

    def _prebaked_session(self, tmp_path: Path) -> GameSession:
        from engine.background_pool import BackgroundEntry

        s = GameSession.new_game("Alex Morgan", seed=1)
        s.init_backgrounds(tmp_path / "bg", prebaked=True)
        # Simulate a baked canonical graph for suburban_house.
        mf = s.background_manifest
        desc = s._descriptor_for(
            LocationCue(spec_id="suburban_house", node_name="kitchen")
        )
        mf.create_graph("suburban_house", desc, graph_id="suburban_house")
        mf.attach_alternate(
            "suburban_house", "kitchen",
            BackgroundEntry(
                entry_id="sh_kitchen_0", descriptor=desc,
                spec_id="suburban_house", node_name="kitchen",
                image_paths=["x/kitchen.png"],
            ),
        )
        return s

    def test_marquee_cue_redirects_to_canonical(self, tmp_path: Path):
        s = self._prebaked_session(tmp_path)
        bp = _house_blueprint(graph_id="player_home", node="kitchen")
        assert s.resolve_scene(bp, {}) == ("suburban_house", "kitchen")

    def test_adhoc_cue_redirects_to_canonical(self, tmp_path: Path):
        s = self._prebaked_session(tmp_path)
        bp = _house_blueprint(graph_id=None, node="kitchen")
        # Not a fresh uuid graph — the canonical spec graph.
        assert s.resolve_scene(bp, {}) == ("suburban_house", "kitchen")

    def test_release_does_not_close_canonical_graph(self, tmp_path: Path):
        s = self._prebaked_session(tmp_path)
        s.release_scene("suburban_house", close=True)
        assert s.background_manifest.get_graph("suburban_house").closed is False


class TestFigureLayoutFor:
    """Phase 23: figure selection + layout integration on the session."""

    def _session(self, tmp_path):
        from engine.figures import (
            FigureAppearance, FigureAsset, FigureCategory, FigureManifest,
            FigurePosture,
        )
        s = GameSession.new_game("Alex Morgan", seed=1)
        s.init_backgrounds(tmp_path / "bg", prebaked=True)
        mf = FigureManifest(assets_root=tmp_path / "figures")
        mf.add(FigureAsset(FigureCategory.PLAYER, FigureAppearance(),
                           FigurePosture.NEUTRAL, "player.png"))
        mf.add(FigureAsset(FigureCategory.INTERLOCUTOR,
                           FigureAppearance(gender="masculine"),
                           FigurePosture.TENSE, "npc.png"))
        s.figure_manifest = mf
        return s

    def _blueprint(self, tone):
        from engine.event_taxonomy import (
            EventDomain, EventId, EventNature, EventTone,
        )
        from engine.events import EventBlueprint, RoleSlot, SceneBlock

        return EventBlueprint(
            id="t.fig",
            tags={"conflict"},
            participants=[
                RoleSlot(role="player", filter=lambda c: c.id == "player"),
                RoleSlot(role="target", filter=lambda c: c.id != "player"),
            ],
            blocks=[SceneBlock(id="main")],
            outcomes={},
            event_id=EventId(
                nature=EventNature.CONFRONTATION,
                domain=EventDomain.RELATIONSHIP,
                tone=tone,
            ),
        )

    def test_returns_player_anchor_last_and_npc(self, tmp_path):
        from engine.event_taxonomy import EventTone

        s = self._session(tmp_path)
        chars = list(s.state.characters.values())
        player = s.state.characters["player"]
        other = next(c for c in chars if c.id != "player")
        cast = {"player": player, "target": other}
        placements = s.figure_layout_for(self._blueprint(EventTone.HOSTILE),
                                         cast, 1280, 720)
        roles = [r for _, _, r in placements]
        assert "player" in roles and "npc" in roles
        assert roles[-1] == "player"  # drawn on top
        # Player anchor is foreground-left, larger than canvas (cropped).
        player_box = next(b for _, b, r in placements if r == "player")
        assert player_box.height > 720

    def test_empty_when_no_figure_pack(self, tmp_path):
        from engine.event_taxonomy import EventTone

        s = GameSession.new_game("Alex Morgan", seed=1)
        s.init_backgrounds(tmp_path / "bg", prebaked=True)
        s.figure_manifest = None
        cast = {"player": s.state.characters["player"]}
        assert s.figure_layout_for(self._blueprint(EventTone.WARM),
                                   cast, 1280, 720) == []
