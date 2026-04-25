"""Background generator orchestration: visit, attach, prefetch, adopt.

The generator is the only thing that produces `BackgroundEntry` objects.
The manifest is generation-agnostic; this module turns story-side calls
(`get_background(graph_id, node_name)`) into images on disk plus
prefetch work scheduled for adjacent nodes.

Two seams:

- ``ImageProducer`` — actually paints pixels. The prototype implementation
  ``PlaceholderImageProducer`` writes a solid-colour PNG with text so the
  rest of the pipeline is testable without ComfyUI. A real implementation
  wraps SD3.5 + img2img with the anchor image.

- ``PrefetchScheduler`` — decides *when* prefetch jobs run. The inline
  implementation runs synchronously (good for tests and single-thread
  prototypes); a deferred implementation queues callables and drains on
  game-loop ticks; the no-op implementation drops prefetch entirely.

The hot path (`get_background`) blocks only on the *requested* node.
Adjacent nodes are scheduled after the requested image is ready, so the
story never waits for prefetch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .background_pool import (
    BackgroundEntry,
    BackgroundManifest,
    LocationDescriptor,
    SceneGraphSpec,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BackgroundGenerationError(RuntimeError):
    """Raised when an image producer fails to produce an image."""


# ---------------------------------------------------------------------------
# Image producer seam
# ---------------------------------------------------------------------------


class ImageProducer(Protocol):
    """Paints one node's image to disk.

    Implementations get the node's descriptor + spec + an optional
    `anchor_path` (the absolute filesystem path of a sibling image
    already attached to the same graph) and write a PNG to `out_path`.
    `variant_index` is 0 for the primary image and ≥1 for subtle-motion
    variants generated against the primary as the img2img anchor;
    real producers should drive it via low-denoise prompt suffixes
    so variants stay near-identical to the primary.
    """

    def produce(
        self,
        *,
        descriptor: LocationDescriptor,
        spec: SceneGraphSpec,
        node_name: str,
        seed: int,
        anchor_path: Path | None,
        out_path: Path,
        variant_index: int = 0,
    ) -> None: ...


@dataclass
class PlaceholderImageProducer:
    """Prototype producer — writes a solid-colour PNG with a label.

    Useful for tests and for running the engine before the SD pipeline
    is wired in. Colour is derived from `(descriptor.bucket_key, seed)`
    so the same graph's rooms share a hue family. ``variant_index``
    nudges hue and brightness slightly so variants are visibly distinct
    while staying recognisable as the same room — same property the
    real img2img variants will produce.
    """

    width: int = 1280
    height: int = 720

    def produce(
        self,
        *,
        descriptor: LocationDescriptor,
        spec: SceneGraphSpec,
        node_name: str,
        seed: int,
        anchor_path: Path | None,
        out_path: Path,
        variant_index: int = 0,
    ) -> None:
        from PIL import Image, ImageDraw, ImageFont

        # Hue family from bucket key; per-node tint from node name;
        # small variant offset so motion variants read as near-identical.
        bucket_seed = abs(hash(descriptor.bucket_key())) % 360
        node_seed = abs(hash(node_name)) % 60
        hue = (bucket_seed + node_seed + variant_index * 6) % 360
        value = max(0.65, min(0.95, 0.85 - variant_index * 0.05))
        rgb = _hsv_to_rgb(hue, 0.4, value)

        img = Image.new("RGB", (self.width, self.height), rgb)
        draw = ImageDraw.Draw(img)
        label = f"{spec.spec_id} / {node_name}"
        sub = (
            f"seed={seed}  variant={variant_index}  anchor="
            f"{anchor_path.name if anchor_path else 'none'}"
        )
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        draw.text((40, 40), label, fill=(20, 20, 20), font=font)
        draw.text((40, 80), sub, fill=(60, 60, 60), font=font)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out_path), "PNG")


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    import colorsys

    r, g, b = colorsys.hsv_to_rgb(h / 360.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


# ---------------------------------------------------------------------------
# Prefetch scheduler seam
# ---------------------------------------------------------------------------


class PrefetchScheduler(Protocol):
    """Decides when prefetch jobs run."""

    def schedule(self, fn: Callable[[], None]) -> None: ...


@dataclass
class InlinePrefetchScheduler:
    """Runs prefetch jobs synchronously. Default for tests and prototype."""

    def schedule(self, fn: Callable[[], None]) -> None:
        fn()


@dataclass
class DeferredPrefetchScheduler:
    """Queues prefetch callables; the caller drains on game-loop ticks.

    Suitable wiring for the future async generator: the simulation
    `narrate_outcome` returns immediately; the Ren'Py outer loop calls
    ``drain(max_items=1)`` between screens to advance prefetch one job
    at a time without ever blocking the player.
    """

    _queue: list[Callable[[], None]] = field(default_factory=list)

    def schedule(self, fn: Callable[[], None]) -> None:
        self._queue.append(fn)

    def drain(self, max_items: int | None = None) -> int:
        ran = 0
        while self._queue and (max_items is None or ran < max_items):
            job = self._queue.pop(0)
            job()
            ran += 1
        return ran

    def pending(self) -> int:
        return len(self._queue)


@dataclass
class NoOpPrefetchScheduler:
    """Drops prefetch jobs — for tests asserting hot-path behaviour only."""

    def schedule(self, fn: Callable[[], None]) -> None:
        return None


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


MAX_VARIANTS_PER_NODE = 3


@dataclass
class BackgroundGenerator:
    """Orchestrates lookup, generation, attachment, and prefetch.

    Holds a registry of authored ``SceneGraphSpec`` keyed by spec id.
    The story drives generation through ``get_background``; prefetch,
    adoption, and visit-driven variant promotion are internal concerns
    triggered as side effects.
    """

    manifest: BackgroundManifest
    specs: dict[str, SceneGraphSpec]
    producer: ImageProducer
    prefetch_scheduler: PrefetchScheduler = field(
        default_factory=InlinePrefetchScheduler
    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_background(self, graph_id: str, node_name: str) -> Path:
        """Return the absolute path to the node's primary image,
        generating it if needed.

        Marks the node visited (incrementing visit count), schedules
        adjacent unattached nodes for prefetch, and schedules variant
        generation when the visit count crosses the next threshold.
        Adjacent prefetch and variant work happen *after* the requested
        image is on disk so the story never waits for background work.
        """
        graph = self.manifest.get_graph(graph_id)
        if graph is None:
            raise KeyError(f"unknown graph_id: {graph_id!r}")
        spec = self._spec_for(graph.spec_id)
        if node_name not in spec.nodes:
            raise KeyError(
                f"node {node_name!r} not in spec {spec.spec_id!r}"
            )

        existing = self.manifest.get_attached(graph_id, node_name)
        if existing is None:
            existing = self._materialise(graph_id, node_name, spec)
        self.manifest.mark_visited(graph_id, node_name)
        self._schedule_neighbors(graph_id, node_name, spec)
        self._schedule_variant_promotion(graph_id, node_name)
        return self.manifest.resolve(existing.primary_path)

    def get_variants(self, graph_id: str, node_name: str) -> list[Path]:
        """Return absolute paths to all variants attached to a node.

        Index 0 is the primary; later indices are subtle-motion variants
        used for crossfade. Returns an empty list if the node isn't
        attached. Does not generate, mark visited, or schedule —
        callers needing on-demand generation should hit
        ``get_background`` first.
        """
        entry = self.manifest.get_attached(graph_id, node_name)
        if entry is None:
            return []
        return [self.manifest.resolve(p) for p in entry.image_paths]

    def prefetch_node(self, graph_id: str, node_name: str) -> None:
        """Generate `node_name`'s primary image if not yet attached.

        No visit, no further prefetch — this is the single-step worker
        that the scheduler runs in the background. Variants are produced
        by ``generate_variant`` separately, never by this method.
        """
        graph = self.manifest.get_graph(graph_id)
        if graph is None or graph.closed:
            return
        spec = self._spec_for(graph.spec_id)
        if node_name not in spec.nodes:
            return
        if self.manifest.get_attached(graph_id, node_name) is not None:
            return
        self._materialise(graph_id, node_name, spec)

    def generate_variant(self, graph_id: str, node_name: str) -> BackgroundEntry | None:
        """Append a subtle-motion variant to an existing node.

        No-op when the node has no primary yet (variants need an
        anchor), when the variant cap is reached, or when the graph is
        closed. The primary image is always the img2img anchor so
        variants stay near-identical — light shift, swaying foliage,
        candle flicker, never a different camera angle.
        """
        graph = self.manifest.get_graph(graph_id)
        if graph is None or graph.closed:
            return None
        entry = self.manifest.get_attached(graph_id, node_name)
        if entry is None:
            return None
        if len(entry.image_paths) >= MAX_VARIANTS_PER_NODE:
            return None
        spec = self._spec_for(graph.spec_id)

        variant_index = len(entry.image_paths)
        anchor_path = self.manifest.resolve(entry.primary_path)
        seed = entry.seed + _variant_seed_offset(variant_index)

        rel_dir = Path(entry.descriptor.bucket_key()) / graph_id
        rel_path = str(rel_dir / f"{node_name}_v{variant_index}.png")
        abs_path = self.manifest.assets_root / rel_path

        try:
            self.producer.produce(
                descriptor=entry.descriptor,
                spec=spec,
                node_name=node_name,
                seed=seed,
                anchor_path=anchor_path,
                out_path=abs_path,
                variant_index=variant_index,
            )
        except Exception as exc:
            raise BackgroundGenerationError(
                f"variant producer failed for graph={graph_id!r} "
                f"node={node_name!r} index={variant_index}: {exc}"
            ) from exc

        if not abs_path.exists():
            raise BackgroundGenerationError(
                f"variant producer for graph={graph_id!r} node={node_name!r} "
                f"index={variant_index} did not write {abs_path}"
            )

        entry.image_paths.append(rel_path)
        return entry

    def warm_node(
        self,
        graph_id: str,
        node_name: str,
        *,
        target_variants: int = MAX_VARIANTS_PER_NODE,
    ) -> None:
        """Schedule the primary plus enough variants to reach the target.

        Used for eager marquee warmup at session boot — schedules the
        primary first (if missing), then variants in order. All work
        flows through the prefetch scheduler so the call returns
        immediately.
        """
        target_variants = max(1, min(target_variants, MAX_VARIANTS_PER_NODE))
        existing = self.manifest.get_attached(graph_id, node_name)
        existing_count = len(existing.image_paths) if existing is not None else 0
        if existing is None:
            self.prefetch_scheduler.schedule(
                _bind(self.prefetch_node, graph_id, node_name)
            )
            existing_count = 1  # primary scheduled
        for _ in range(target_variants - existing_count):
            self.prefetch_scheduler.schedule(
                _bind(self.generate_variant, graph_id, node_name)
            )

    # ------------------------------------------------------------------
    # Internal — spec lookup
    # ------------------------------------------------------------------

    def _spec_for(self, spec_id: str) -> SceneGraphSpec:
        spec = self.specs.get(spec_id)
        if spec is None:
            raise KeyError(f"unknown scene graph spec_id: {spec_id!r}")
        return spec

    # ------------------------------------------------------------------
    # Internal — adoption + generation
    # ------------------------------------------------------------------

    def _materialise(
        self, graph_id: str, node_name: str, spec: SceneGraphSpec
    ) -> BackgroundEntry:
        graph = self.manifest.get_graph(graph_id)
        assert graph is not None  # checked by caller

        # Cold-start adoption: empty graph may absorb a matching pool entry.
        if not graph.node_entries:
            adoptable = self.manifest.find_adoptable(
                graph.descriptor, node_name
            )
            if adoptable is not None:
                return self.manifest.adopt(graph_id, adoptable.entry_id)

        return self._generate_fresh(graph_id, node_name, spec)

    def _generate_fresh(
        self, graph_id: str, node_name: str, spec: SceneGraphSpec
    ) -> BackgroundEntry:
        graph = self.manifest.get_graph(graph_id)
        assert graph is not None
        descriptor = graph.descriptor

        # Pick anchor: any sibling already attached. None for first node.
        anchors = self.manifest.graph_anchor_entries(graph_id)
        anchor_entry = anchors[0] if anchors else None
        anchor_path = (
            self.manifest.resolve(anchor_entry.primary_path)
            if anchor_entry is not None
            else None
        )

        # Deterministic seed: bucket hash + graph + node.
        seed = _seed_for(descriptor, graph_id, node_name)

        entry_id = self.manifest.next_entry_id(descriptor, node_name)
        rel_dir = Path(descriptor.bucket_key()) / graph_id
        rel_path = str(rel_dir / f"{node_name}.png")
        abs_path = self.manifest.assets_root / rel_path

        try:
            self.producer.produce(
                descriptor=descriptor,
                spec=spec,
                node_name=node_name,
                seed=seed,
                anchor_path=anchor_path,
                out_path=abs_path,
                variant_index=0,
            )
        except Exception as exc:  # noqa: BLE001 — surface the underlying cause
            raise BackgroundGenerationError(
                f"image producer failed for graph={graph_id!r} "
                f"node={node_name!r}: {exc}"
            ) from exc

        if not abs_path.exists():
            raise BackgroundGenerationError(
                f"image producer for graph={graph_id!r} node={node_name!r} "
                f"did not write {abs_path}"
            )

        entry = BackgroundEntry(
            entry_id=entry_id,
            descriptor=descriptor,
            spec_id=spec.spec_id,
            node_name=node_name,
            image_paths=[rel_path],
            seed=seed,
            anchor_entry_id=anchor_entry.entry_id if anchor_entry else None,
        )
        return self.manifest.attach_entry(graph_id, node_name, entry)

    # ------------------------------------------------------------------
    # Internal — prefetch scheduling
    # ------------------------------------------------------------------

    def _schedule_neighbors(
        self, graph_id: str, node_name: str, spec: SceneGraphSpec
    ) -> None:
        for neighbor in spec.neighbors(node_name):
            if self.manifest.get_attached(graph_id, neighbor) is not None:
                continue
            # Bind args at schedule time so deferred queues capture the right values.
            self.prefetch_scheduler.schedule(
                _bind(self.prefetch_node, graph_id, neighbor)
            )

    def _schedule_variant_promotion(self, graph_id: str, node_name: str) -> None:
        """Lazily generate variants once visit count crosses thresholds.

        Visit 1 keeps the single primary; visit 2 schedules variant 1
        in the background; visit 3 schedules variant 2; visits 4+ are
        no-ops (the cap is ``MAX_VARIANTS_PER_NODE``).
        """
        graph = self.manifest.get_graph(graph_id)
        if graph is None or graph.closed:
            return
        entry = self.manifest.get_attached(graph_id, node_name)
        if entry is None:
            return
        count = graph.visit_counts.get(node_name, 0)
        target = min(count, MAX_VARIANTS_PER_NODE)
        for _ in range(target - len(entry.image_paths)):
            self.prefetch_scheduler.schedule(
                _bind(self.generate_variant, graph_id, node_name)
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_for(
    descriptor: LocationDescriptor, graph_id: str, node_name: str
) -> int:
    import hashlib

    payload = f"{descriptor.bucket_key()}|{graph_id}|{node_name}"
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _variant_seed_offset(variant_index: int) -> int:
    """Stable per-variant seed offset so variants render distinct
    motion frames without collapsing to the primary's pixels."""
    import hashlib

    h = hashlib.sha256(f"variant:{variant_index}".encode("utf-8")).hexdigest()
    return int(h[:6], 16)


def _bind(fn: Callable, *args) -> Callable[[], None]:
    def _call() -> None:
        fn(*args)

    return _call
