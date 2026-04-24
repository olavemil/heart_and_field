"""Arc traversal — blueprint graph walking (technical §5.3, §7).

An *arc* is a chain of related events linked via prerequisite/unlock edges
and the ``carries_arc_context`` flag. This module provides utilities to:

- build a lightweight directed graph from a set of blueprints,
- query which events belong to a given arc chain,
- find the most recent arc outcome for context chaining.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .events import EventBlueprint
from .outcomes import OutcomeRecord


# --- Arc graph ---------------------------------------------------------------


@dataclass
class ArcNode:
    """One node in the arc dependency graph."""

    event_id: str
    carries_arc_context: bool
    unlocks: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    disables: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "carries_arc_context": self.carries_arc_context,
            "unlocks": list(self.unlocks),
            "prerequisites": list(self.prerequisites),
            "disables": list(self.disables),
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "ArcNode":
        return cls(
            event_id=d["event_id"],
            carries_arc_context=bool(d.get("carries_arc_context", False)),
            unlocks=list(d.get("unlocks", [])),
            prerequisites=list(d.get("prerequisites", [])),
            disables=list(d.get("disables", [])),
        )


@dataclass
class ArcGraph:
    """Directed graph of event dependencies, built from blueprints."""

    nodes: dict[str, ArcNode] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"nodes": {k: v.to_dict() for k, v in self.nodes.items()}}

    @classmethod
    def from_dict(cls, d: Mapping) -> "ArcGraph":
        return cls(
            nodes={
                k: ArcNode.from_dict(v) for k, v in d.get("nodes", {}).items()
            }
        )


def build_arc_graph(blueprints: Sequence[EventBlueprint]) -> ArcGraph:
    """Build an arc graph from a list of blueprints."""
    nodes: dict[str, ArcNode] = {}
    for bp in blueprints:
        nodes[bp.id] = ArcNode(
            event_id=bp.id,
            carries_arc_context=bp.carries_arc_context,
            unlocks=list(bp.unlocks),
            prerequisites=list(bp.prerequisites),
            disables=list(bp.disables),
        )
    return ArcGraph(nodes=nodes)


# --- Arc chain queries -------------------------------------------------------


def arc_chain(graph: ArcGraph, start_id: str) -> list[str]:
    """Return the ordered chain of event IDs reachable forward from *start_id*
    via unlock edges. Includes *start_id* itself.

    Performs a simple BFS on ``unlocks`` edges. Guards against cycles.
    """
    if start_id not in graph.nodes:
        return []
    visited: list[str] = []
    queue = [start_id]
    seen: set[str] = set()
    while queue:
        eid = queue.pop(0)
        if eid in seen:
            continue
        seen.add(eid)
        visited.append(eid)
        node = graph.nodes.get(eid)
        if node is not None:
            for unlocked in node.unlocks:
                if unlocked not in seen:
                    queue.append(unlocked)
    return visited


def arc_roots(graph: ArcGraph) -> list[str]:
    """Return event IDs that are arc roots — they carry arc context and have
    no prerequisites (i.e. they start a chain)."""
    return [
        eid
        for eid, node in graph.nodes.items()
        if node.carries_arc_context and not node.prerequisites
    ]


def arc_events(graph: ArcGraph) -> list[str]:
    """Return all event IDs that carry arc context."""
    return [
        eid for eid, node in graph.nodes.items() if node.carries_arc_context
    ]


def find_prior_arc_outcome(
    event_id: str,
    graph: ArcGraph,
    outcome_log: Sequence[OutcomeRecord],
) -> OutcomeRecord | None:
    """Find the most recent outcome that belongs to the same arc chain as
    *event_id* and carries arc context.

    Walks prerequisite edges backward to find chain members, then scans the
    log in reverse for the latest matching outcome.
    """
    # Gather all event IDs in this arc chain by walking prerequisites backward.
    chain_ids: set[str] = set()
    queue = [event_id]
    seen: set[str] = set()
    while queue:
        eid = queue.pop(0)
        if eid in seen:
            continue
        seen.add(eid)
        node = graph.nodes.get(eid)
        if node is None:
            continue
        if node.carries_arc_context:
            chain_ids.add(eid)
        for prereq in node.prerequisites:
            if prereq not in seen:
                queue.append(prereq)
        # Also walk forward via unlocks to capture the full chain.
        for unlocked in node.unlocks:
            if unlocked not in seen:
                queue.append(unlocked)

    # Remove the event itself — we want the *prior* outcome.
    chain_ids.discard(event_id)

    if not chain_ids:
        return None

    # Scan log in reverse for the most recent arc-context outcome.
    for outcome in reversed(outcome_log):
        if outcome.event_id in chain_ids and outcome.arc_summary is not None:
            return outcome
    return None
