"""Background pool: location descriptor, scene graphs, manifest, adoption.

A **scene graph** is a coherent location instance (e.g. *Charlene's house*).
Its **spec** declares which named nodes can exist (front_door, living_room,
bathroom, …) and how they're adjacent — adjacency drives prefetch but the
engine never enforces traversal (the story can jump anywhere). The story
references nodes by name within a graph instance; rooms within the same
graph share visual identity.

A **`BackgroundEntry`** is one image bound to one node of one graph. The
first entry attached to a graph anchors visual identity; subsequent
entries in the same graph are generated using earlier siblings as the
img2img anchor (style + palette + lighting carry across).

Lifecycle:

1. `create_graph(spec_id, descriptor)` produces an empty `SceneGraphInstance`.
2. The generator calls `attach_entry(graph_id, node_name, entry)` whenever
   it produces an image — synchronously for the requested node, in the
   background for adjacent nodes.
3. The story calls `mark_visited(graph_id, node_name)` when it actually
   shows the image. Unvisited prefetched entries are tentative.
4. `release_graph(graph_id)` ends the graph's life: visited entries stay
   bound forever; unvisited entries detach (`graph_id → None`) and join the
   adoption pool.
5. A *cold-start* graph with no anchors can adopt a pool entry whose
   descriptor + node-name match — the adopted entry becomes the new
   graph's first anchor.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping


# ---------------------------------------------------------------------------
# Descriptor — location-creator axes = adoption key
# ---------------------------------------------------------------------------


class LocationKind(str, Enum):
    SUBURBAN_HOUSE = "suburban_house"
    APARTMENT = "apartment"
    SCHOOL = "school"
    GYM = "gym"
    LOCKER_ROOM = "locker_room"
    TEAM_HQ = "team_hq"
    TRAINING_GROUND = "training_ground"
    NEIGHBORHOOD = "neighborhood"
    CAFE = "cafe"
    BAR = "bar"
    MEDIA = "media"
    TRANSIT = "transit"
    PARK = "park"
    STADIUM = "stadium"


class Era(str, Enum):
    MODERN = "modern"
    RETRO_90S = "retro_90s"
    RETRO_80S = "retro_80s"


class Socioeconomic(str, Enum):
    MODEST = "modest"
    COMFORTABLE = "comfortable"
    AFFLUENT = "affluent"


class MoodTone(str, Enum):
    WARM = "warm"
    NEUTRAL = "neutral"
    COLD = "cold"


@dataclass(frozen=True)
class LocationDescriptor:
    """The location-creator's lever set — anything affecting the silhouette
    of a place across all its rooms.

    Two graphs sharing the same `bucket_key` can adopt entries from each
    other's pool (after release). `appearance_details` is free-text that
    participates only by hash so authoring specifics don't collide.
    """

    kind: LocationKind = LocationKind.SUBURBAN_HOUSE
    era: Era = Era.MODERN
    socioeconomic: Socioeconomic = Socioeconomic.COMFORTABLE
    mood: MoodTone = MoodTone.NEUTRAL
    palette: str = ""  # short style cue, e.g. "warm oak, beige walls"
    appearance_details: str = ""  # free-text anchoring

    def bucket_key(self) -> str:
        parts = [
            self.kind.value,
            self.era.value,
            self.socioeconomic.value,
            self.mood.value,
        ]
        if self.palette:
            parts.append("p" + hashlib.sha256(
                self.palette.encode("utf-8")
            ).hexdigest()[:6])
        if self.appearance_details:
            parts.append("d" + hashlib.sha256(
                self.appearance_details.encode("utf-8")
            ).hexdigest()[:6])
        return "_".join(parts)

    def short_hash(self) -> str:
        h = hashlib.sha256(self.bucket_key().encode("utf-8")).hexdigest()
        return h[:8]

    def to_prompt_fragment(self) -> str:
        """Natural-language description for the generation prompt."""
        kind_readable = self.kind.value.replace("_", " ")
        era_map = {
            Era.MODERN: "contemporary",
            Era.RETRO_90S: "1990s period",
            Era.RETRO_80S: "1980s period",
        }
        socio_map = {
            Socioeconomic.MODEST: "modest, lived-in",
            Socioeconomic.COMFORTABLE: "comfortable middle-class",
            Socioeconomic.AFFLUENT: "well-appointed",
        }
        mood_map = {
            MoodTone.WARM: "warm inviting atmosphere",
            MoodTone.NEUTRAL: "natural light",
            MoodTone.COLD: "cool detached atmosphere",
        }
        fragments = [
            f"{era_map[self.era]} {kind_readable}",
            socio_map[self.socioeconomic],
            mood_map[self.mood],
        ]
        if self.palette:
            fragments.append(self.palette)
        if self.appearance_details:
            fragments.append(self.appearance_details)
        return ", ".join(fragments)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "era": self.era.value,
            "socioeconomic": self.socioeconomic.value,
            "mood": self.mood.value,
            "palette": self.palette,
            "appearance_details": self.appearance_details,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "LocationDescriptor":
        return cls(
            kind=LocationKind(d.get("kind", LocationKind.SUBURBAN_HOUSE.value)),
            era=Era(d.get("era", Era.MODERN.value)),
            socioeconomic=Socioeconomic(
                d.get("socioeconomic", Socioeconomic.COMFORTABLE.value)
            ),
            mood=MoodTone(d.get("mood", MoodTone.NEUTRAL.value)),
            palette=str(d.get("palette", "")),
            appearance_details=str(d.get("appearance_details", "")),
        )


# ---------------------------------------------------------------------------
# Scene graph spec — authored schema for a kind of place
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SceneGraphSpec:
    """Schema declaring which nodes a graph of this kind can have.

    `adjacency` is undirected: authors should list the relationship from
    one side; `neighbors()` mirrors automatically. `entry_nodes` are the
    nodes the story is allowed to enter from outside (typically a single
    establishing shot like `front_door` or `street_view`).
    """

    spec_id: str
    kind: LocationKind
    nodes: tuple[str, ...]
    adjacency: tuple[tuple[str, str], ...] = ()
    entry_nodes: tuple[str, ...] = ()
    # Per-node count of distinct *alternate* compositions (Phase 23). A
    # tuple of ``(node, count)`` pairs (kept tuple-shaped so the spec
    # stays frozen/hashable); nodes absent here have a single alternate.
    # Distinct alternates are different shots chosen per visit — separate
    # from the motion variants inside one entry's ``image_paths``.
    alternates: tuple[tuple[str, int], ...] = ()

    def __post_init__(self):
        node_set = set(self.nodes)
        if not node_set:
            raise ValueError(f"spec {self.spec_id!r} has no nodes")
        for a, b in self.adjacency:
            if a not in node_set or b not in node_set:
                raise ValueError(
                    f"adjacency edge {(a, b)!r} references unknown node "
                    f"in spec {self.spec_id!r}"
                )
        for n in self.entry_nodes:
            if n not in node_set:
                raise ValueError(
                    f"entry node {n!r} not in spec {self.spec_id!r}"
                )
        for node, count in self.alternates:
            if node not in node_set:
                raise ValueError(
                    f"alternates entry {node!r} not in spec {self.spec_id!r}"
                )
            if count < 1:
                raise ValueError(
                    f"alternate count for {node!r} must be >= 1, got {count}"
                )

    def alternate_count(self, node: str) -> int:
        """How many distinct alternate shots a node has (default 1)."""
        for n, count in self.alternates:
            if n == node:
                return count
        return 1

    def neighbors(self, node: str) -> tuple[str, ...]:
        """Return nodes adjacent to `node`, treating adjacency as undirected."""
        if node not in self.nodes:
            raise KeyError(f"unknown node {node!r} in spec {self.spec_id!r}")
        out: list[str] = []
        for a, b in self.adjacency:
            if a == node and b not in out:
                out.append(b)
            elif b == node and a not in out:
                out.append(a)
        return tuple(out)


# ---------------------------------------------------------------------------
# Background entry — one image, optionally bound to a graph slot
# ---------------------------------------------------------------------------


@dataclass
class BackgroundEntry:
    """A generated background image set.

    `image_paths[0]` is the primary; `image_paths[1:]` are variants
    used for subtle-motion crossfade. New entries start with one path;
    variants are appended on visit-driven promotion or eager marquee
    warmup. `graph_id` holds the current owner; `None` means the entry
    is in the adoption pool. `visited` records whether the story
    actually showed this image (vs prefetched-but-unused).
    """

    entry_id: str
    descriptor: LocationDescriptor
    spec_id: str
    node_name: str
    image_paths: list[str] = field(default_factory=list)
    seed: int = 0
    anchor_entry_id: str | None = None  # which sibling's image anchored this
    graph_id: str | None = None
    visited: bool = False

    @property
    def primary_path(self) -> str:
        return self.image_paths[0]

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "descriptor": self.descriptor.to_dict(),
            "spec_id": self.spec_id,
            "node_name": self.node_name,
            "image_paths": list(self.image_paths),
            "seed": self.seed,
            "anchor_entry_id": self.anchor_entry_id,
            "graph_id": self.graph_id,
            "visited": self.visited,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "BackgroundEntry":
        # Accept both old single-path and new list shape so older
        # manifests on disk reload without migration.
        if "image_paths" in d:
            image_paths = [str(p) for p in d["image_paths"]]
        elif "image_path" in d:
            image_paths = [str(d["image_path"])]
        else:
            image_paths = []
        return cls(
            entry_id=str(d["entry_id"]),
            descriptor=LocationDescriptor.from_dict(d["descriptor"]),
            spec_id=str(d["spec_id"]),
            node_name=str(d["node_name"]),
            image_paths=image_paths,
            seed=int(d.get("seed", 0)),
            anchor_entry_id=d.get("anchor_entry_id"),
            graph_id=d.get("graph_id"),
            visited=bool(d.get("visited", False)),
        )


# ---------------------------------------------------------------------------
# Scene graph instance — one realised location in the manifest
# ---------------------------------------------------------------------------


@dataclass
class SceneGraphInstance:
    """One concrete scene graph (e.g. *Charlene's house*).

    `node_entries` maps node names to `entry_id`s. The graph is empty at
    creation; entries arrive lazily as the story (or prefetch) calls into
    them. `visit_counts` tracks how many times each node has been visited
    by the story — generators read this to drive lazy variant promotion.
    `closed` is set when `release_graph` runs — closed graphs are
    immutable and act as historical records.
    """

    graph_id: str
    spec_id: str
    descriptor: LocationDescriptor
    node_entries: dict[str, str] = field(default_factory=dict)
    visit_counts: dict[str, int] = field(default_factory=dict)
    closed: bool = False
    # Per-node list of alternate entry_ids (Phase 23). Index 0 mirrors
    # ``node_entries[node]`` (the primary); 1.. are extra distinct shots.
    # Empty for on-demand graphs, which behave as single-alternate; the
    # pre-bake path populates it. Kept parallel to ``node_entries`` so the
    # on-demand lazy/adoption machinery stays untouched.
    node_alternates: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "graph_id": self.graph_id,
            "spec_id": self.spec_id,
            "descriptor": self.descriptor.to_dict(),
            "node_entries": dict(self.node_entries),
            "visit_counts": dict(self.visit_counts),
            "closed": self.closed,
            "node_alternates": {k: list(v) for k, v in self.node_alternates.items()},
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "SceneGraphInstance":
        return cls(
            graph_id=str(d["graph_id"]),
            spec_id=str(d["spec_id"]),
            descriptor=LocationDescriptor.from_dict(d["descriptor"]),
            node_entries=dict(d.get("node_entries", {})),
            visit_counts=dict(d.get("visit_counts", {})),
            closed=bool(d.get("closed", False)),
            node_alternates={
                str(k): [str(e) for e in v]
                for k, v in d.get("node_alternates", {}).items()
            },
        )


# ---------------------------------------------------------------------------
# Manifest — pure data store, no generation knowledge
# ---------------------------------------------------------------------------


DEFAULT_MANIFEST_NAME = "manifest.json"


@dataclass
class BackgroundManifest:
    """JSON-backed store of background entries and graph instances.

    The manifest is intentionally generation-agnostic: a generator
    creates `BackgroundEntry` objects and calls `attach_entry`; the
    manifest tracks ownership, visitation, and the adoption pool.
    """

    assets_root: Path
    entries: list[BackgroundEntry] = field(default_factory=list)
    graphs: list[SceneGraphInstance] = field(default_factory=list)
    manifest_path: Path | None = None

    # --- Paths ---------------------------------------------------------

    def _path(self) -> Path:
        return self.manifest_path or (self.assets_root / DEFAULT_MANIFEST_NAME)

    def resolve(self, relative_path: str) -> Path:
        return self.assets_root / relative_path

    # --- Persistence ---------------------------------------------------

    def save(self) -> Path:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "entries": [e.to_dict() for e in self.entries],
            "graphs": [g.to_dict() for g in self.graphs],
        }
        path.write_text(json.dumps(payload, indent=2))
        return path

    @classmethod
    def load(
        cls, assets_root: Path, manifest_path: Path | None = None
    ) -> "BackgroundManifest":
        mf = cls(assets_root=Path(assets_root), manifest_path=manifest_path)
        path = mf._path()
        if path.exists():
            payload = json.loads(path.read_text())
            mf.entries = [
                BackgroundEntry.from_dict(e) for e in payload.get("entries", [])
            ]
            mf.graphs = [
                SceneGraphInstance.from_dict(g) for g in payload.get("graphs", [])
            ]
        return mf

    # --- Entry lookup --------------------------------------------------

    def get_entry(self, entry_id: str) -> BackgroundEntry | None:
        for e in self.entries:
            if e.entry_id == entry_id:
                return e
        return None

    def next_entry_id(
        self, descriptor: LocationDescriptor, node_name: str
    ) -> str:
        """Stable, human-readable id for a new entry in this bucket+node."""
        prefix = f"{descriptor.bucket_key()}__{node_name}"
        existing = sum(
            1
            for e in self.entries
            if e.descriptor.bucket_key() == descriptor.bucket_key()
            and e.node_name == node_name
        )
        return f"{prefix}_{existing}"

    # --- Graph lookup --------------------------------------------------

    def get_graph(self, graph_id: str) -> SceneGraphInstance | None:
        for g in self.graphs:
            if g.graph_id == graph_id:
                return g
        return None

    def create_graph(
        self,
        spec_id: str,
        descriptor: LocationDescriptor,
        *,
        graph_id: str | None = None,
    ) -> SceneGraphInstance:
        """Add a new empty graph instance.

        `graph_id` is auto-generated when omitted (ad-hoc graphs); marquee
        locations should pass an authored stable id like ``"player_home"``.
        """
        if graph_id is None:
            graph_id = f"{spec_id}_{uuid.uuid4().hex[:8]}"
        if self.get_graph(graph_id) is not None:
            raise ValueError(f"duplicate graph_id: {graph_id!r}")
        graph = SceneGraphInstance(
            graph_id=graph_id, spec_id=spec_id, descriptor=descriptor
        )
        self.graphs.append(graph)
        return graph

    # --- Attach / visit / release --------------------------------------

    def attach_entry(
        self, graph_id: str, node_name: str, entry: BackgroundEntry
    ) -> BackgroundEntry:
        """Bind an entry to a graph slot. Generators call this.

        The entry is added to the manifest if not already present, then
        bound to `(graph_id, node_name)`. Visitation stays at its current
        value — `mark_visited` is the explicit story-side signal.
        """
        graph = self.get_graph(graph_id)
        if graph is None:
            raise KeyError(f"unknown graph_id: {graph_id!r}")
        if graph.closed:
            raise RuntimeError(f"graph {graph_id!r} is closed")
        if node_name in graph.node_entries:
            raise RuntimeError(
                f"graph {graph_id!r} already has node {node_name!r} attached"
            )
        if self.get_entry(entry.entry_id) is None:
            self.entries.append(entry)
        entry.graph_id = graph_id
        entry.node_name = node_name
        graph.node_entries[node_name] = entry.entry_id
        return entry

    def get_attached(
        self, graph_id: str, node_name: str
    ) -> BackgroundEntry | None:
        graph = self.get_graph(graph_id)
        if graph is None:
            return None
        entry_id = graph.node_entries.get(node_name)
        if entry_id is None:
            return None
        return self.get_entry(entry_id)

    def mark_visited(self, graph_id: str, node_name: str) -> BackgroundEntry:
        """Record that the story showed this node and bump its visit count.

        Sets ``visited=True`` on the entry (idempotent) and increments
        the graph's per-node visit counter (monotonically increasing).
        Generators read the counter to drive lazy variant promotion.
        """
        entry = self.get_attached(graph_id, node_name)
        if entry is None:
            raise KeyError(
                f"no entry attached at graph={graph_id!r} node={node_name!r}"
            )
        entry.visited = True
        graph = self.get_graph(graph_id)
        if graph is not None:
            graph.visit_counts[node_name] = graph.visit_counts.get(node_name, 0) + 1
        return entry

    # --- Alternates (Phase 23, pre-bake path) --------------------------

    def attach_alternate(
        self, graph_id: str, node_name: str, entry: BackgroundEntry
    ) -> BackgroundEntry:
        """Append a distinct alternate shot for a node.

        Unlike :meth:`attach_entry` (one-per-node, on-demand), this builds
        the per-node alternate list. The first alternate also becomes the
        node's primary ``node_entries`` binding so all existing
        single-entry consumers (anchors, ``get_attached``) keep working.
        """
        graph = self.get_graph(graph_id)
        if graph is None:
            raise KeyError(f"unknown graph_id: {graph_id!r}")
        if graph.closed:
            raise RuntimeError(f"graph {graph_id!r} is closed")
        if self.get_entry(entry.entry_id) is None:
            self.entries.append(entry)
        entry.graph_id = graph_id
        entry.node_name = node_name
        alts = graph.node_alternates.setdefault(node_name, [])
        if entry.entry_id not in alts:
            alts.append(entry.entry_id)
        if node_name not in graph.node_entries:
            graph.node_entries[node_name] = entry.entry_id
        return entry

    def get_alternates(
        self, graph_id: str, node_name: str
    ) -> list[BackgroundEntry]:
        """All alternate entries for a node, primary first.

        Falls back to the single ``node_entries`` binding for on-demand
        graphs that never populated ``node_alternates``.
        """
        graph = self.get_graph(graph_id)
        if graph is None:
            return []
        ids = graph.node_alternates.get(node_name)
        if not ids:
            single = self.get_attached(graph_id, node_name)
            return [single] if single is not None else []
        return [
            self.get_entry(eid)
            for eid in ids
            if self.get_entry(eid) is not None
        ]

    def choose_alternate(
        self, graph_id: str, node_name: str, visit_index: int
    ) -> BackgroundEntry | None:
        """Pick one alternate deterministically by visit index.

        Rotates through the alternates so revisits vary rather than
        repeat; reproducible from the (saved) visit count.
        """
        alts = self.get_alternates(graph_id, node_name)
        if not alts:
            return None
        return alts[visit_index % len(alts)]

    def graph_anchor_entries(self, graph_id: str) -> list[BackgroundEntry]:
        """Entries already attached to this graph — used as img2img anchors."""
        graph = self.get_graph(graph_id)
        if graph is None:
            return []
        return [
            self.get_entry(eid)
            for eid in graph.node_entries.values()
            if self.get_entry(eid) is not None
        ]

    def reap_unvisited(self, graph_id: str) -> list[BackgroundEntry]:
        """Detach unvisited entries from `graph_id` into the adoption pool.

        Use after an event ends to flush prefetched-but-unused images so
        a future cold-start graph can adopt them. The graph itself stays
        open — marquee locations (`player_home`, `school`) call this many
        times across the season without closing.

        Returns the detached entries.
        """
        graph = self.get_graph(graph_id)
        if graph is None:
            raise KeyError(f"unknown graph_id: {graph_id!r}")
        if graph.closed:
            return []
        released: list[BackgroundEntry] = []
        kept: dict[str, str] = {}
        for node_name, entry_id in graph.node_entries.items():
            entry = self.get_entry(entry_id)
            if entry is None:
                continue
            if entry.visited:
                kept[node_name] = entry_id
            else:
                entry.graph_id = None
                released.append(entry)
        graph.node_entries = kept
        return released

    def close_graph(self, graph_id: str) -> None:
        """Mark a graph closed — no further attachments allowed.

        Idempotent. Call after an ad-hoc graph's event ends so the next
        "some teammate's house" event creates a fresh graph instead of
        re-using this one.
        """
        graph = self.get_graph(graph_id)
        if graph is None:
            raise KeyError(f"unknown graph_id: {graph_id!r}")
        graph.closed = True

    def release_graph(self, graph_id: str) -> list[BackgroundEntry]:
        """Reap unvisited entries and close the graph in one step.

        Equivalent to ``reap_unvisited`` followed by ``close_graph`` — the
        ad-hoc lifecycle endpoint. Marquee graphs should call
        ``reap_unvisited`` directly to keep the graph open.
        """
        released = self.reap_unvisited(graph_id)
        self.close_graph(graph_id)
        return released

    # --- Adoption pool -------------------------------------------------

    def find_adoptable(
        self, descriptor: LocationDescriptor, node_name: str
    ) -> BackgroundEntry | None:
        """Return a pool entry matching `(descriptor.bucket_key, node_name)`.

        The match is exact: pool lookups are predictable, not fuzzy.
        Returns the oldest unattached match so the pool drains FIFO.
        """
        key = descriptor.bucket_key()
        for entry in self.entries:
            if entry.graph_id is not None:
                continue
            if entry.node_name != node_name:
                continue
            if entry.descriptor.bucket_key() != key:
                continue
            return entry
        return None

    def adopt(
        self, graph_id: str, entry_id: str
    ) -> BackgroundEntry:
        """Bind a pool entry to a cold-start graph as its anchor.

        Raises if the graph already has any attached entries — adoption
        only makes sense before anchors are established (the adopted
        entry's style would otherwise clash with existing siblings).
        """
        graph = self.get_graph(graph_id)
        if graph is None:
            raise KeyError(f"unknown graph_id: {graph_id!r}")
        if graph.closed:
            raise RuntimeError(f"graph {graph_id!r} is closed")
        if graph.node_entries:
            raise RuntimeError(
                f"graph {graph_id!r} already has anchors; cannot adopt"
            )
        entry = self.get_entry(entry_id)
        if entry is None:
            raise KeyError(f"unknown entry_id: {entry_id!r}")
        if entry.graph_id is not None:
            raise RuntimeError(f"entry {entry_id!r} already bound")
        entry.graph_id = graph_id
        graph.node_entries[entry.node_name] = entry.entry_id
        return entry

    # --- Iteration helpers --------------------------------------------

    def pool_entries(self) -> list[BackgroundEntry]:
        return [e for e in self.entries if e.graph_id is None]

    def graph_entries(self, graph_id: str) -> list[BackgroundEntry]:
        return [e for e in self.entries if e.graph_id == graph_id]

    def unattached_nodes(
        self, graph_id: str, spec: SceneGraphSpec
    ) -> list[str]:
        """Nodes in the spec that aren't yet attached to this graph."""
        graph = self.get_graph(graph_id)
        if graph is None:
            raise KeyError(f"unknown graph_id: {graph_id!r}")
        return [n for n in spec.nodes if n not in graph.node_entries]
