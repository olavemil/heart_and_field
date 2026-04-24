"""Tests for engine.arcs — arc graph building and traversal."""

from engine.arcs import (
    ArcGraph,
    ArcNode,
    arc_chain,
    arc_events,
    arc_roots,
    build_arc_graph,
    find_prior_arc_outcome,
)
from engine.events import BranchOutcome, EventBlueprint
from engine.outcomes import OutcomeRecord, WeekPhase


def _bp(
    id: str,
    prereqs: list[str] | None = None,
    unlocks: list[str] | None = None,
    disables: list[str] | None = None,
    carries_arc: bool = False,
) -> EventBlueprint:
    return EventBlueprint(
        id=id,
        prerequisites=prereqs or [],
        unlocks=unlocks or [],
        disables=disables or [],
        carries_arc_context=carries_arc,
        outcomes={"default": BranchOutcome(summary=f"{id} happened")},
    )


class TestBuildArcGraph:
    def test_builds_from_blueprints(self):
        bps = [
            _bp("a", unlocks=["b"], carries_arc=True),
            _bp("b", prereqs=["a"], unlocks=["c"], carries_arc=True),
            _bp("c", prereqs=["b"]),
        ]
        graph = build_arc_graph(bps)
        assert len(graph.nodes) == 3
        assert graph.nodes["a"].unlocks == ["b"]
        assert graph.nodes["b"].prerequisites == ["a"]
        assert graph.nodes["a"].carries_arc_context is True
        assert graph.nodes["c"].carries_arc_context is False

    def test_round_trip(self):
        bps = [
            _bp("x", unlocks=["y"], carries_arc=True),
            _bp("y", prereqs=["x"], disables=["z"]),
            _bp("z"),
        ]
        graph = build_arc_graph(bps)
        d = graph.to_dict()
        restored = ArcGraph.from_dict(d)
        assert len(restored.nodes) == 3
        assert restored.nodes["x"].unlocks == ["y"]
        assert restored.nodes["y"].disables == ["z"]


class TestArcChain:
    def test_linear_chain(self):
        bps = [
            _bp("a", unlocks=["b"]),
            _bp("b", prereqs=["a"], unlocks=["c"]),
            _bp("c", prereqs=["b"]),
        ]
        graph = build_arc_graph(bps)
        chain = arc_chain(graph, "a")
        assert chain == ["a", "b", "c"]

    def test_single_node(self):
        graph = build_arc_graph([_bp("solo")])
        assert arc_chain(graph, "solo") == ["solo"]

    def test_unknown_start(self):
        graph = build_arc_graph([_bp("a")])
        assert arc_chain(graph, "missing") == []

    def test_branching_chain(self):
        bps = [
            _bp("root", unlocks=["b1", "b2"]),
            _bp("b1", prereqs=["root"]),
            _bp("b2", prereqs=["root"], unlocks=["c"]),
            _bp("c", prereqs=["b2"]),
        ]
        graph = build_arc_graph(bps)
        chain = arc_chain(graph, "root")
        assert "root" in chain
        assert "b1" in chain
        assert "b2" in chain
        assert "c" in chain

    def test_cycle_safety(self):
        bps = [
            _bp("a", unlocks=["b"]),
            _bp("b", unlocks=["a"]),  # cycle!
        ]
        graph = build_arc_graph(bps)
        chain = arc_chain(graph, "a")
        assert chain == ["a", "b"]  # no infinite loop


class TestArcRoots:
    def test_finds_roots(self):
        bps = [
            _bp("root1", unlocks=["b"], carries_arc=True),
            _bp("root2", carries_arc=True),
            _bp("b", prereqs=["root1"], carries_arc=True),
            _bp("standalone"),
        ]
        graph = build_arc_graph(bps)
        roots = arc_roots(graph)
        assert sorted(roots) == ["root1", "root2"]

    def test_no_roots(self):
        bps = [_bp("a"), _bp("b")]
        graph = build_arc_graph(bps)
        assert arc_roots(graph) == []


class TestArcEvents:
    def test_finds_arc_events(self):
        bps = [
            _bp("a", carries_arc=True),
            _bp("b"),
            _bp("c", carries_arc=True),
        ]
        graph = build_arc_graph(bps)
        assert sorted(arc_events(graph)) == ["a", "c"]


class TestFindPriorArcOutcome:
    def _outcome(
        self, event_id: str, arc_summary: str | None = None
    ) -> OutcomeRecord:
        return OutcomeRecord(
            event_id=event_id,
            timestamp=WeekPhase(1, 1),
            participants={},
            branch_taken="default",
            summary=f"{event_id} summary",
            arc_summary=arc_summary,
        )

    def test_finds_prior_in_chain(self):
        bps = [
            _bp("a", unlocks=["b"], carries_arc=True),
            _bp("b", prereqs=["a"], carries_arc=True),
        ]
        graph = build_arc_graph(bps)
        log = [self._outcome("a", arc_summary="A happened")]
        prior = find_prior_arc_outcome("b", graph, log)
        assert prior is not None
        assert prior.event_id == "a"
        assert prior.arc_summary == "A happened"

    def test_returns_most_recent(self):
        bps = [
            _bp("a", unlocks=["b"], carries_arc=True),
            _bp("b", prereqs=["a"], unlocks=["c"], carries_arc=True),
            _bp("c", prereqs=["b"], carries_arc=True),
        ]
        graph = build_arc_graph(bps)
        log = [
            self._outcome("a", arc_summary="first"),
            self._outcome("b", arc_summary="first. second"),
        ]
        prior = find_prior_arc_outcome("c", graph, log)
        assert prior is not None
        assert prior.event_id == "b"

    def test_no_prior_for_root(self):
        bps = [_bp("root", carries_arc=True)]
        graph = build_arc_graph(bps)
        prior = find_prior_arc_outcome("root", graph, [])
        assert prior is None

    def test_ignores_unrelated_outcomes(self):
        bps = [
            _bp("a", unlocks=["b"], carries_arc=True),
            _bp("b", prereqs=["a"], carries_arc=True),
            _bp("unrelated", carries_arc=True),
        ]
        graph = build_arc_graph(bps)
        log = [self._outcome("unrelated", arc_summary="not related")]
        prior = find_prior_arc_outcome("b", graph, log)
        assert prior is None
