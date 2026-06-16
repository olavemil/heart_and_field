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


@dataclass
class PrebakedImageProducer:
    """Read-only producer for shipped pre-baked asset packs (Phase 23).

    Never generates. In a correctly-packaged build every requested image
    already exists on disk (attached in the shipped manifest), so the
    serving path returns paths directly and ``produce`` is never called.
    If it *is* called, that's a packaging gap:

    - ``strict=True`` (dev/CI) raises so the missing asset is surfaced.
    - ``strict=False`` (shipped) writes a placeholder so a gap degrades
      gracefully rather than crashing play.
    """

    strict: bool = False
    width: int = 1280
    height: int = 720
    _fallback: "PlaceholderImageProducer" = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._fallback = PlaceholderImageProducer(
            width=self.width, height=self.height
        )

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
        if self.strict:
            raise FileNotFoundError(
                "pre-baked asset missing: "
                f"{spec.spec_id}/{node_name} variant={variant_index} "
                f"(expected at {out_path})"
            )
        self._fallback.produce(
            descriptor=descriptor,
            spec=spec,
            node_name=node_name,
            seed=seed,
            anchor_path=anchor_path,
            out_path=out_path,
            variant_index=variant_index,
        )


# ---------------------------------------------------------------------------
# ComfyUI image producer
# ---------------------------------------------------------------------------


# Node-level prompt phrases. Each node name gets a supplementary fragment
# that steers the generation toward the right composition.
_NODE_PROMPT_HINTS: dict[str, str] = {
    "front_door": "exterior entrance view, door and porch, street visible",
    "living_room": "living room interior, sofa and coffee table",
    "kitchen": "kitchen interior, counters and cabinets",
    "bedroom": "bedroom interior, bed and nightstand",
    "bathroom": "bathroom interior, sink and mirror",
    "hallway": "narrow hallway interior, doors on both sides",
    "courtyard": "outdoor courtyard, paved ground, building walls around",
    "classroom": "classroom interior, desks and whiteboard",
    "locker_bay": "row of lockers in corridor, school setting",
    "gym": "indoor gymnasium, wooden floor, high ceiling",
    "office": "small office interior, desk and chair, shelves",
    "street_view": "street exterior, buildings and pavement",
    "bar_counter": "bar counter interior, bottles and stools",
    "dining_area": "dining area, tables with chairs, ambient lighting",
    "lobby": "hotel or building lobby, reception area",
    "balcony": "balcony exterior, railing, view of surroundings",
    # Hot-tier authored nodes (Phase 23)
    "locker_room": "team locker room interior, benches and lockers, kit hanging",
    "garden": "back garden exterior, lawn and fencing, planting",
    "entrance": "apartment entrance hall just inside the door, coat hooks",
    "recreation": "team recreation room, sofas, pool table, relaxed",
    "showers": "communal shower room, tiled walls, steam",
    "manager_office": "football manager's office, desk, tactics board, trophies",
    "conference_room": "club conference room, long table, presentation screen",
    "training_ground": "outdoor football training pitch, cones and goals, daylight",
    "pitch": "football pitch from pitchside, stadium stands behind, daylight",
    "coffee_shop": "cosy coffee shop interior, counter, small tables, warm light",
    "bakery": "bakery cafe interior, display case of bread and pastries, counter",
    "bar": "warm pub interior, bar counter and stools, low evening light",
    "press_room": "press conference room, backdrop board, microphones, seating",
    "team_bus": "team coach bus interior, seats along the aisle, motorway window light",
}

# Validated painterly recipe (spike, June 2026): a loose impressionistic
# style + the negative prompt below are what lifted output from the flat
# "DOS pixel-art" look and fixed incoherent geometry (Escher bathroom).
# "detailed/sharp" cues pushed the wrong way and were removed. Keep the
# SD3 default sampler (euler/sgm_uniform) — off-combo samplers NaN to black.
_BG_PROMPT_PREFIX = (
    "loose painterly digital painting, impressionistic, soft visible "
    "brushwork, atmospheric, muted natural palette, soft focus, evocative "
    "mood, visual-novel background art, wide angle, no people, no text, "
)
_BG_NEGATIVE_PROMPT = (
    "pixel art, dithering, 8-bit, retro game, low resolution, sharp hard "
    "edges, crisp linework, 3d render, cgi, plastic, photorealistic, text, "
    "watermark, logo, people, person, faces, distorted geometry, warped "
    "perspective, duplicated fixtures, extra sinks, extra doors, "
    "floating objects, clutter, nsfw"
)

# Variant generation uses low denoise to keep spatial layout identical
# while introducing subtle ambient shifts (flickering light, swaying
# curtains, shifting shadows).
_VARIANT_DENOISE = 0.35
_VARIANT_PROMPT_SUFFIX = ", subtle ambient variation, slightly different lighting"


@dataclass
class ComfyUIImageProducer:
    """Real image producer backed by ComfyUI.

    Primary images (variant_index=0):
    - Without anchor: txt2img from descriptor + node prompt.
    - With anchor: img2img from anchor with moderate denoise (0.65) so
      the new room inherits palette and lighting from its sibling.

    Variants (variant_index >= 1):
    - img2img from the primary image at low denoise (0.35) for subtle
      ambient motion (light flicker, shadow shift).

    Falls back to ``PlaceholderImageProducer`` when ComfyUI returns None.
    """

    client: "ComfyUIClient"
    width: int = 1280
    height: int = 720
    primary_steps: int = 32
    primary_cfg: float = 4.5
    # Denoise for anchored primaries — high enough to change composition,
    # low enough to lock palette and lighting family.
    anchor_denoise: float = 0.65
    variant_steps: int = 20
    variant_cfg: float = 4.5
    variant_denoise: float = _VARIANT_DENOISE
    _fallback: PlaceholderImageProducer = field(init=False)

    def __post_init__(self) -> None:
        self._fallback = PlaceholderImageProducer(
            width=self.width, height=self.height
        )

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
        prompt = self._build_prompt(descriptor, node_name)

        if variant_index > 0:
            image_bytes = self._produce_variant(
                prompt, seed=seed, anchor_path=anchor_path or out_path
            )
        elif anchor_path is not None:
            image_bytes = self._produce_anchored(
                prompt, seed=seed, anchor_path=anchor_path
            )
        else:
            image_bytes = self._produce_fresh(prompt, seed=seed)

        if image_bytes is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(image_bytes)
        else:
            # ComfyUI unavailable or errored — fall back to placeholder
            self._fallback.produce(
                descriptor=descriptor,
                spec=spec,
                node_name=node_name,
                seed=seed,
                anchor_path=anchor_path,
                out_path=out_path,
                variant_index=variant_index,
            )

    # ------------------------------------------------------------------
    # Internal generation paths
    # ------------------------------------------------------------------

    def _produce_fresh(self, prompt: str, *, seed: int) -> bytes | None:
        """txt2img — first node in a graph, no anchor."""
        return self.client.txt2img(
            prompt,
            negative_prompt=_BG_NEGATIVE_PROMPT,
            seed=seed,
            width=self.width,
            height=self.height,
            steps=self.primary_steps,
            cfg=self.primary_cfg,
            denoise=1.0,
            filename_prefix="fh_bg",
        )

    def _produce_anchored(
        self, prompt: str, *, seed: int, anchor_path: Path
    ) -> bytes | None:
        """img2img from a sibling node's image — inherits palette/lighting."""
        uploaded_name = self._upload_anchor(anchor_path)
        if uploaded_name is None:
            return None
        return self.client.img2img(
            prompt,
            input_image=uploaded_name,
            negative_prompt=_BG_NEGATIVE_PROMPT,
            seed=seed,
            width=self.width,
            height=self.height,
            steps=self.primary_steps,
            cfg=self.primary_cfg,
            denoise=self.anchor_denoise,
            filename_prefix="fh_bg",
        )

    def _produce_variant(
        self, prompt: str, *, seed: int, anchor_path: Path
    ) -> bytes | None:
        """img2img at low denoise — subtle ambient shift."""
        uploaded_name = self._upload_anchor(anchor_path)
        if uploaded_name is None:
            return None
        variant_prompt = prompt + _VARIANT_PROMPT_SUFFIX
        return self.client.img2img(
            variant_prompt,
            input_image=uploaded_name,
            negative_prompt=_BG_NEGATIVE_PROMPT,
            seed=seed,
            width=self.width,
            height=self.height,
            steps=self.variant_steps,
            cfg=self.variant_cfg,
            denoise=self.variant_denoise,
            filename_prefix="fh_bgv",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _upload_anchor(self, anchor_path: Path) -> str | None:
        """Read anchor image from disk and upload to ComfyUI."""
        if not anchor_path.exists():
            return None
        image_bytes = anchor_path.read_bytes()
        return self.client.upload_image(image_bytes, anchor_path.name)

    @staticmethod
    def _build_prompt(descriptor: LocationDescriptor, node_name: str) -> str:
        """Compose the generation prompt from descriptor + node hints."""
        base = descriptor.to_prompt_fragment()
        node_hint = _NODE_PROMPT_HINTS.get(node_name, node_name.replace("_", " "))
        return f"{_BG_PROMPT_PREFIX}{base}, {node_hint}"


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
    # Transient: which alternate ``get_background`` last served per
    # (graph, node), so ``get_variants`` returns the matching crossfade
    # set. Not persisted — repopulated on the next serve after a load.
    _active_alternate: dict[tuple[str, str], str] = field(
        default_factory=dict, init=False, repr=False
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

        # Pick the alternate for this visit from the *pre-increment* count
        # so revisits rotate. choose_alternate falls back to the single
        # binding for on-demand graphs; None means nothing attached yet.
        visit_index = graph.visit_counts.get(node_name, 0)
        chosen = self.manifest.choose_alternate(graph_id, node_name, visit_index)
        if chosen is None:
            chosen = self.manifest.get_attached(graph_id, node_name)
            if chosen is None:
                chosen = self._materialise(graph_id, node_name, spec)
        # Remember the served alternate so get_variants stays consistent.
        self._active_alternate[(graph_id, node_name)] = chosen.entry_id
        self.manifest.mark_visited(graph_id, node_name)
        self._schedule_neighbors(graph_id, node_name, spec)
        self._schedule_variant_promotion(graph_id, node_name)
        return self.manifest.resolve(chosen.primary_path)

    def get_variants(self, graph_id: str, node_name: str) -> list[Path]:
        """Return absolute paths to the variants of the *currently served*
        alternate — primary at index 0, subtle-motion variants after.

        Reads the alternate ``get_background`` last served for this node
        so the crossfade frames belong to the shown shot. Falls back to
        the node's primary binding if no serve has happened yet. Returns
        an empty list if the node isn't attached. Does not generate, mark
        visited, or schedule — call ``get_background`` first.
        """
        eid = self._active_alternate.get((graph_id, node_name))
        entry = (
            self.manifest.get_entry(eid)
            if eid is not None
            else None
        )
        if entry is None:
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
