# Design: Build-Time Pre-Baked Rendering

Status: **proposed** (design only — no implementation yet)
Date: 2026-06-15
Supersedes runtime on-demand generation as the default distribution path.

## Context

Today visuals are generated **on demand at runtime**: `init_backgrounds`
wires a `ComfyUIImageProducer`, and `get_background` (the `scene_path`
hot path) synchronously generates a node's image on first access,
caching it to disk and prefetching neighbours. Characters render through
`VisualManager.render_character` against a stock face pool / procedural
layers.

This forces every player to install ComfyUI, download multi-GB Flux/SD
models, and own a capable GPU; it adds first-access latency, makes
quality nondeterministic and hard to QA, and slows warm-up.

The architecture already separates three axes, which makes a strategy
swap cheap:

- **WHAT** — `BackgroundManifest` + `SceneGraphSpec` nodes
  (`game/content/scenes/`), and the character axes
  (age × build × gender) in `engine/visual.py` / `engine/stock_faces.py`.
- **WHEN** — `PrefetchScheduler` + the `get_background` hot path.
- **WHERE/HOW** — the `ImageProducer` protocol
  (`ComfyUIImageProducer` vs `PlaceholderImageProducer`).

On-demand is one point in WHEN×WHERE space. Everything downstream loads
from a disk cache keyed by the manifest.

## Decision

Adopt **full build-time pre-baking** as the shipped default:

1. A dev/CI step generates **every** background (spec × node × instance ×
   variant) and the **stock character face pool** offline via ComfyUI,
   writing PNGs plus a manifest into a versioned asset pack.
2. The asset pack ships in the distribution.
3. At runtime the game loads the pack **read-only** — no ComfyUI, no GPU,
   no runtime generation. Determinism, instant access, full QA.
4. On-demand generation is retained only as an **opt-in dev/author mode**
   (and the placeholder producer remains the no-assets fallback).

Trade-off accepted: a fixed location/character set and a larger download,
in exchange for zero player setup and deterministic, QA-able visuals.

## Current state to build on

- `generate_art.py` (root) — batch faces/overlays/backgrounds via
  ComfyUI, but uses a **hardcoded `CHARACTERS` dict** and the legacy flat
  `BACKGROUND_PROMPTS`, writing to `game/generated/`. Not manifest-aware.
- `scripts/generate_sprites.py` — descriptor-driven two-step sprite
  pipeline with presets.
- `scripts/generate_stock_faces.py` — stock face pool keyed by
  age×build×gender buckets.
- Runtime: `GameSession.init_backgrounds(... producer=, comfyui_client=,
  prefetch_scheduler=)` already lets us inject the producer/scheduler.
- Grades (`color_grades.py`) and noise overlays (`overlays.py`) are
  **already deterministic solid-PNG bakes** at `init_backgrounds` — they
  are NOT SD and need no change beyond shipping them in the pack.

The work is consolidating the three ad-hoc generators into one
**manifest-driven** pre-bake, and adding a read-only runtime producer.

## The bounded asset set

**Backgrounds** = for each `SceneGraphSpec` in `game/content/scenes/`:
`spec × node × applicable SceneInstance × variant(0..N)`.

- Today: 2 specs × 6 nodes = 12 base nodes.
- Instances: 13 `SceneInstance` values, but each applies only to
  scene-types where its `descriptor_overrides_for_instance` is relevant —
  not a full cross-product. Enumeration must be driven by which
  `(spec, node, instance)` triples blueprints actually request via
  `LocationCue` (marquee `graph_id` + `node_name` + optional
  `scene_instance`) plus the default (no-instance) render of every node.
- Variants: promotion caps at 3 per node (Phase 11A).

**Characters** = stock face pool keyed by `age_group(3) × build(3) ×
gender_presentation(3)` = 27 buckets × *k* faces/bucket, assigned to
procedural NPCs deterministically by character ID (the
[[sprite_pipeline_decision]] direction). Expression overlays stay
procedural/cheap.

**Rough size estimate (to confirm with a counting spike):** ~36–72
background PNGs now (12 nodes × ~1–2 instances × ~3 variants) and ~80–135
pool faces (27 buckets × 3–5). At ~0.5–1 MB per 1280×720 PNG that is
tens of MB today, scaling roughly linearly with authored specs toward a
few hundred MB at full content. **This estimate is the main open
question** and should be nailed down before committing (see Open
questions).

## File-level changes

### New: read-only runtime producer

`game/engine/background_generator.py`

- Add `PrebakedImageProducer` implementing the `ImageProducer` protocol.
  `produce(...)` raises / returns a sentinel if an asset is missing
  rather than generating — pre-baked play should never hit a missing
  asset, and a missing one is a packaging bug we want surfaced (in dev)
  or gracefully placeholdered (in shipped builds, configurable).
- It performs **no** ComfyUI calls and needs no client.

### New: manifest-driven pre-bake CLI

`scripts/prebake_assets.py` (consolidates `generate_art.py` +
`generate_sprites.py` + `generate_stock_faces.py`)

- Loads scene specs via `load_scene_specs_from_path` and blueprints via
  `load_blueprints_from_path`, enumerates every required
  `(spec, node, instance, variant)` from blueprint `LocationCue`s + each
  spec's full node set.
- Drives `ComfyUIImageProducer` (the existing one) offline to render each
  into the asset-pack dir, writing a `manifest.json` the runtime loads.
- Renders the stock face pool (27 buckets × k) via the existing stock
  pipeline.
- Deterministic seeds per `(graph/node/instance/variant)` and per face
  bucket index, so re-runs reproduce identical assets and partial re-bakes
  are possible.
- `--dry-run` prints the full asset list + count + size estimate (this is
  also the "counting spike" deliverable).
- Old generators are either deleted or thin-shimmed to call this.

### Runtime wiring

`game/engine/session.py` — `init_backgrounds`

- Add an explicit mode (param or inferred from a shipped manifest):
  - **prebaked** (default shipped): use `PrebakedImageProducer`, load the
    packaged manifest, set the prefetch scheduler to a no-op (nothing to
    generate), skip ComfyUI entirely.
  - **on-demand** (dev/author): current behaviour, opt-in.
  - **placeholder**: unchanged fallback.
- `warm_marquees` becomes a no-op in prebaked mode (everything already on
  disk).

`game/scripts/runtime.rpy` — `fh_init_backgrounds`

- Default to prebaked mode; stop passing `comfyui_client` in the shipped
  path. Character rendering (`visual_display.rpy`) already loads from the
  pool — point it at the packaged pool.

### Manifest as shipped data

- Resolve the deferred "manifest as part of save file" item: the **base**
  manifest ships read-only with the pack; per-save state (visit counts)
  stays in `fh_save_blob`. Confirm `BackgroundManifest` load path can open
  a read-only packaged manifest without rewriting it.

### Packaging

- Asset pack lives under `game/assets/prebaked/` (backgrounds, faces,
  grades, overlays, manifest.json), committed or built in CI and bundled
  by Ren'Py's distribute step. Document the regen command in
  `scripts/check.sh`-adjacent tooling.

## Determinism & seeds

Fixed seed per asset key (already the convention for faces by character
ID). Pre-bake makes determinism total: identical pack across machines,
reproducible in CI. Runtime no longer draws image RNG at all.

## Migration & fallback

- Phase in behind the mode switch; on-demand stays available for authors.
- Shipped builds with a missing asset fall back to placeholder (config
  flag) so a packaging gap degrades gracefully rather than crashing.
- No `.rpy` display-layer changes beyond the producer/mode wiring — the
  composite/ATL path (`scene_compose.rpy`) is unchanged (the whole point
  of the `render()` abstraction seam).

## Testing

- Unit: `PrebakedImageProducer` returns packaged paths, surfaces missing
  assets per config.
- Unit: `prebake_assets.py` enumeration covers every spec node + every
  blueprint `LocationCue` triple (golden count test).
- Integration: a headless session in prebaked mode resolves a scene for
  every blueprint with a cue, with no ComfyUI client present and the
  prefetch scheduler asserted to never run a job.
- Keep the existing on-demand + placeholder tests green (modes coexist).

## Open questions (resolve before implementing)

1. **Asset-pack size** — run `prebake_assets.py --dry-run` (or a small
   counting spike) to get the real combo count and MB estimate. This
   decides whether full pre-bake is comfortable or wants the hybrid
   (B) instead. **Gating question.**
2. **Instance enumeration** — confirm the exact rule for which
   `(node, instance)` pairs are reachable (blueprint-cue-driven vs full
   cross-product). Over-generating instances is the main size risk.
3. **Faces per bucket (k)** — how much NPC visual variety is enough?
   Drives pool size.
4. **Where the pack is built** — committed vs CI artifact vs first-run
   download. Affects repo size and release flow.
5. **Variant count in shipped builds** — ship all 3 variants (breathing
   crossfade) or just the primary to halve background size?

## Appendix A — Background catalogue (nail-down)

Backgrounds do the heavy lifting for colour and immersion and stay on
screen a long time, so they get the budget; faces stay deferred (prior
face experiments were too jarring to commit to). Goal: **high quality,
sufficient variety, ≥2 alternates per known location, more for
frequently-triggered scenes.**

### Two distinct concepts (do not conflate)

- **Alternate** — a genuinely different composition of the same location
  (different angle / framing / time of day), chosen per visit so a
  frequent scene doesn't look identical every time. *This is what
  "2+ options per location" means.* **Requires a model addition** (see
  below) — today the engine only has motion variants.
- **Motion variant** — near-identical crossfade frame of one shot
  (`image_paths[1..N]`, Phase 11A) for subtle life. Orthogonal; a size
  *multiplier* on top of alternates, decided separately (Open Q5).
  **Note (future):** breathing is only worth the cost on scenes where
  minor movement adds value — pitch/tribunes (match-day audience,
  banners), garden/park/street (grass, wind), showers/sauna (steam),
  pool/lakeside (water/waves). Approach: feed the primary back through
  **img2img at strict low denoise** so only minor details regenerate.
  Most interior scenes ship primary-only with no motion variant.

Counts below are **alternates** (distinct shots). Motion variants
multiply the primary-only total later.

### Frequency tiers (from a 15-seed × 6-week sim, scene-type exposure)

| Tier | Exposure | Scene types | Alternates / node |
|------|----------|-------------|-------------------|
| 1 hot | 90–210 | locker_room, training_ground, cafe, pitch, house, apartment | 3–4 |
| 2 mid | 40–90 | park, office, tunnel, gym, restaurant | 2–3 |
| 3 occasional | <40 | boardroom, medical, press_room, bar, club, studio, transit | 2 (floor) |
| 4 not-yet-referenced | 0 | mansion, sauna, lakeside, kiosk, grocery, pool, … | 2 (floor) |

### Catalogue → engine mapping

Each **location type = one `SceneGraphSpec`**; **rooms = nodes**;
**alternates = the new per-node concept**; **team-colour / price-range =
`SceneInstance`-style modifiers**.

**Residences** (biggest; full room set per type, architecturally
consistent across rooms). Rooms: garden/exterior, entrance/hallway,
living/dining, kitchen, bathroom, bedroom, + 1 type-specific extra = 7.

| Residence spec | Tier | Alt/room | Shots |
|----------------|------|----------|-------|
| suburb (house) | 1 | 3 | 21 |
| apartment | 1 | 3 | 21 |
| old_house | 3 | 2 | 14 |
| mansion (+wine cellar) | 4 | 2 | 14 |
| **subtotal** | | | **70** |

(Seasonal variants deferred — a ×2–4 multiplier, revisit after the size
estimate.)

**Sports arena** (team-specific; ≥1 set per sport; colour variants
red/green/blue/gold on the colour-bearing nodes only). Nodes: exterior,
entrance/tunnel, pitch/field, bench/stands.

| | colour-bearing (×4) | neutral (×1) | pitch alt +1×4 | per sport |
|---|---|---|---|---|
| nodes | exterior, pitch, stands | tunnel | pitch | |
| shots | 12 | 1 | +4 | **17** |

3 sports (soccer, rugby, basketball) × 17 = **51**.

**Team HQ** (sport-agnostic; 3 set-styles, player sees one per
playthrough + brief away glimpses). Nodes: locker room, recreational,
showers, manager office, conference room = 5.

| | base (5 × 3 styles) | locker_room hot +3 | total |
|---|---|---|---|
| shots | 15 | +3 | **18** |

**Generic** (mostly single-node locations).

| Location | Tier | Shots |
|----------|------|-------|
| cafe (coffee shop + bakery) | 1 | 6 |
| restaurant (3 price ranges ×2) | 2 | 6 |
| college/high-school (6-node spec ×2) | 2 | 12 |
| park | 2 | 3 |
| pool, sauna, lakeside, kiosk, food stall, grocery | 3–4 | 2 each = 12 |
| **subtotal** | | **39** |

### Totals & size estimate

| Group | Alternate shots |
|-------|-----------------|
| Residences | 70 |
| Sports arenas | 51 |
| Team HQ | 18 |
| Generic | 39 |
| **Total (primary, no motion variants)** | **~178** |

At 1280×720, high-quality PNG ≈ 1–1.5 MB → **~180–270 MB primary-only**.
Motion variants multiply: ×2 ≈ 360–540 MB, ×3 ≈ 540–810 MB. Grades and
overlays add only ~tens of KB (already-deterministic bakes).

### Model addition required: per-node alternates

`game/engine/background_pool.py`

- `SceneGraphSpec` gains per-node alternate counts (e.g.
  `alternates: dict[str, int]`, default 1) so the spec declares how many
  distinct shots a node has.
- `BackgroundEntry` already holds `image_paths`; today index 0 is the
  primary and 1..N are *motion* variants. Introduce a clean separation:
  an **alternate set** (distinct shots) where each alternate may itself
  carry motion variants — e.g. `alternates: list[list[str]]`, or a
  parallel field — so "pick an alternate per visit, crossfade its motion
  variants within the view" stays unambiguous.
- Per-visit alternate choice: deterministic by `(graph_id, node, visit
  index)` or seeded by save, so revisits rotate alternates rather than
  repeating, and saves stay reproducible.
- `prebake_assets.py` generates `alternates × motion_variants` per node;
  the runtime read-only producer just indexes in.

This is the one non-trivial engine change the catalogue implies; the rest
is content (spec authoring) + the pre-bake driver.

## Appendix B — Locked decisions & hot-tier prototype

**Decisions (2026-06-15):**

- **Quality tier:** 1280×720, **primary-only** (no motion variants yet).
  ~180–270 MB at full catalogue; ~80–120 MB for the hot-tier prototype.
- **Prototype scope:** hot tier first — get background + text running,
  validate quality, then scale to the full ~178.
- Faces stay deferred; backgrounds get the budget.
- Motion variants and seasonal variants are post-prototype multipliers.

**Hot-tier prototype set (~70–80 shots):**

| Spec / location | Nodes | Alt/node | Shots |
|-----------------|-------|----------|-------|
| suburb residence | 7 rooms | 3 | 21 |
| apartment residence | 7 rooms | 3 | 21 |
| team HQ (1 style) | 5 rooms (locker_room +3) | 2 (locker 3) | 11 |
| training_ground | 1 | 3 | 3 |
| cafe | coffee + bakery | 3 | 6 |
| pitch (neutral colour) | 1 | 3 | 3 |
| **total** | | | **~65** |

(Round up to ~80 with a couple of park/restaurant shots for variety.)

**Build order (code first; SD bake runs on the dev's ComfyUI):**

1. **Model addition** — per-node *alternates* in
   `background_pool.py`. ✅ **Done (Phase 23A).**
   - `SceneGraphSpec.alternates: tuple[(node, count), …]` (frozen-safe)
     + `alternate_count(node)` (default 1).
   - `SceneGraphInstance.node_alternates: dict[node, list[entry_id]]` —
     a parallel field to `node_entries` (index 0 = primary), so the
     on-demand lazy/adoption machinery is **untouched**; on-demand
     graphs behave as single-alternate. Save round-trips.
   - Manifest API: `attach_alternate`, `get_alternates` (falls back to
     the single binding for on-demand graphs), `choose_alternate(graph,
     node, visit_index)` (rotates by visit count, reproducible).
   - 8 unit tests; 918 total green; on-demand path unaffected.
   - **Deferred to step 2/5 — serving consistency:** `scene_path` and
     `scene_variants` are separate Ren'Py calls and must agree on which
     alternate was chosen (the crossfade variants must belong to the
     shown primary). Pick the alternate from the *pre-increment* visit
     count, then `mark_visited`; remember the served alternate (transient
     per `(graph, node)`) so `scene_variants` returns the matching set.
2. **Read-only producer + alternate serving.** ✅ **Done (Phase 23B).**
   - `PrebakedImageProducer` (`background_generator.py`): never
     generates; `strict=True` raises on a missing asset (dev/CI),
     `strict=False` writes a placeholder (shipped builds degrade
     gracefully). In a correct pack it's never called — serving returns
     attached paths directly.
   - `init_backgrounds(..., prebaked=True)`: `PrebakedImageProducer` +
     `NoOpPrefetchScheduler`, ignores `comfyui_client`, skips marquee
     warm-up (pack manifest is the single source of truth).
   - **Alternate-aware serving** wired into `BackgroundGenerator`:
     `get_background` picks the alternate from the pre-increment visit
     count (rotates on revisit), records it in a transient
     `_active_alternate` map, then `mark_visited`. `get_variants` reads
     that map so the crossfade frames belong to the shown shot — the
     consistency guarantee. On-demand graphs (no alternates) behave
     exactly as before.
   - Tests: alternate rotation, scene_path/scene_variants agreement at
     both generator and session level, prebaked strict/lenient/no-op
     paths, mode wiring. 927 total green; on-demand path unaffected.
   - **Runtime flip deferred to step 5:** `runtime.rpy` still uses the
     on-demand/placeholder path because no pack exists yet. Flip
     `fh_init_backgrounds` to `prebaked=True` once the driver (step 4)
     has produced a pack.
3. **Spec authoring.** ✅ **Done (Phase 23C).**
   - `suburban_house` extended with a `garden` node + 3 alternates/room
     (7 rooms). New `apartment` (6 rooms ×3), `team_hq` (5 rooms,
     locker_room ×3, rest ×2), and `venues.py` (`training_ground` ×3,
     `pitch` ×3, `cafe` with coffee_shop + bakery ×3). Reused existing
     `LocationKind`s (team_hq→LOCKER_ROOM, training→GYM per the existing
     bridge) — no new enum needed.
   - `_NODE_PROMPT_HINTS` extended with every new node (garden, entrance,
     recreation, showers, manager_office, conference_room,
     training_ground, pitch, coffee_shop, bakery, locker_room).
   - **Hot-tier total: 68 alternate shots** (matches the ~65–80
     estimate). Tests assert the specs load, the alternate counts, and
     full prompt-hint coverage (a missing hint would silently degrade a
     prompt). 929 total green.
   - *Boundary note:* node hints still live in `background_generator.py`
     (existing convention). A future cleanup could move per-node prompt
     phrasing onto the spec itself (content), but that's out of scope.
4. **Pre-bake driver.** ✅ **Done (Phase 23D).**
   - `scripts/prebake_assets.py`: enumerates every `spec × node ×
     alternate` (68 shots), creates one graph per spec
     (`graph_id == spec_id`), and bakes each via the locked recipe.
     Reuses `ComfyUIImageProducer._build_prompt` so bake prompts ==
     runtime prompts.
   - **Idempotent**: stable `(spec, node, alt)` → entry-id + path +
     deterministic (hashlib) seed; skips shots already on disk +
     attached. Rerun generates only what's missing (validated: rerun
     leaves 68 PNGs / 68 entries, no dupes). `--force` regenerates,
     `--only SPEC` scopes, `--placeholder` bakes solid PNGs with no GPU,
     `--dry-run` previews the full plan + prompts.
   - Per-spec descriptors (palette/mood/socioeconomic) in the driver;
     node hints carry room specifics.
   - 4 driver tests (placeholder bake, idempotency, `--only`, seed
     determinism). 933 total green.

   **Correction to Appendix B note:** `to_prompt_fragment` *does* emit
   the kind word (`"{era} {kind}"`), so a spec's `LocationKind` leaks
   into every node's prompt. Reusing approximate kinds polluted prompts
   (team HQ's office/showers read "…locker room…"; training read "gym …
   outdoor pitch"). Fixed by adding `LocationKind.TEAM_HQ` /
   `TRAINING_GROUND` — a live demo of the "add a kind" cost: 1 enum
   value + 1 required bridge row (`_LOCATION_KIND_TO_SCENE_TYPE`, pinned
   by the `for kind in LocationKind` test) + an optional overlays row
   (defaults to grain) + an optional reverse-bridge row. No
   architectural churn; adding a kind now also *improves* prompts.
5. **Bake + wire** — run the driver, point runtime at the pack, play
   background + text end-to-end.

Steps 1–4 are implementable and testable headlessly now; step 5 needs
the dev's ComfyUI (port 8000) and produces the actual images. The
placeholder producer keeps the prototype playable before the bake.

## Appendix C — Locked generation recipe (validated)

A spike (`scripts/prebake_spike*.py`, 6 scenes) dialled in quality and
**this recipe is now baked into `ComfyUIImageProducer` +
`background_generator.py` prompt constants** (910 tests green):

- **Sampler:** `euler` / `sgm_uniform` — **never override.** SD3.5-medium
  NaNs to a black image on off-combo samplers (`dpmpp_2m`/`karras`
  produced black + 120s timeouts in testing).
- **Style prefix** (`_BG_PROMPT_PREFIX`): loose painterly / impressionistic
  / soft brushwork / muted / soft-focus. The old "detailed environment"
  cue pushed toward the flat "DOS pixel-art" look and was removed.
- **Negative prompt** (`_BG_NEGATIVE_PROMPT`, now forwarded through
  `txt2img`/`img2img`): `pixel art, … sharp hard edges, cgi,
  photorealistic, … distorted geometry, duplicated fixtures, extra
  sinks, …`. **This was the single biggest quality lever** — it fixed
  both the pixelation and the incoherent geometry (Escher bathroom).
- **Steps 32, cfg 4.5, 1280×720.** Client `DEFAULT_TIMEOUT` 120→**300s**
  (a 32-step 720p render takes ~130–150s; 120 was too low and was the
  real cause of the v2 batch timeouts).
- **Colour pinning** for team scenes — e.g. "Green team → green lockers,
  benches, branding throughout" produced coherent single-colour kit
  rather than random multicolour accessories.

**Throughput implication:** ~130–150s/image → the ~80-shot hot-tier is
~3 hrs, the full ~178 catalogue ~6–7 hrs of offline generation. Batch
overnight; reserve the "generate N, keep best" reject pass for the
hottest/longest-on-screen scenes rather than 3× across the board.

Quality verdict (operator-reviewed): bathroom, house entrance, park,
cantina ship-quality; pitch (match-day crowd) and locker room (green-
pinned) good. Approved to proceed to the catalogue build.

## Appendix D — Coverage review & Phase 23E (gap specs + backlog)

Cross-referenced the location wishlist against blueprint
`valid_scene_types`. Scene-type **order** matters: `_cue_from_scene_types`
resolves the first type that maps to a loaded spec, so a later type is
"shadowed" if an earlier one already resolves.

### Authored now (Phase 23E) — true gaps

Events fired here but resolved wrong or blank:

| Spec | Kind (new) | Was | Now | Events |
|------|-----------|-----|-----|--------|
| `bar` | BAR | a cafe | a pub | `rel.team_night_out` (club→BAR too) |
| `media` | MEDIA | a school | press room | `external.media_scrum`, `inst.award_ceremony`, `secret.forced_reveal` (studio→MEDIA too) |
| `transit` | TRANSIT | blank | team bus | `downtime.travel_reading` (car/plane→TRANSIT too) |

3 single-node specs (2 alternates each, +6 shots → 74 total). 4th "add a
LocationKind" demo: BAR/MEDIA/TRANSIT each = enum + bridge rows + overlay
row; bridge funnels related scene types so one background serves the
family. `to_prompt_fragment` kind words read fine ("contemporary bar /
media / transit" + node hint).

### Shadowed — NOT gaps (no action needed)

These scene types are referenced but a preceding type always resolves
first, so the event already gets a sensible background:

- `medical` → shadowed by `locker_room` (`vuln.injury_worry` shows the
  locker room).
- `tunnel` → shadowed by `locker_room` (`pregame.locker_room_speech`,
  `rel.overheard_truth`).
- `gym` → shadowed by `training_ground` (`sport.solo_warmdown`,
  `training.drill_partner`).

To make any of these *primary*, reorder the blueprint's
`valid_scene_types` (content edit) — then author the spec. Cheap, but a
deliberate authoring choice, deferred.

### Content backlog — backgrounds wanting events (Tier 2/3)

Authored-background-without-events opportunities (need new blueprints to
pay off):

- **Mansion** — wealth disparity / agent / sponsor; status contrast.
  `SceneType.MANSION` exists, 0 blueprints.
- **Sauna / pool / lakeside** — recovery, vulnerability, bonding. (POOL,
  BEACH enum types exist, unused.)
- **Kiosk / grocery / food stall** — mundane texture, chance encounters;
  `personal.kind_stranger` would slot in (currently cafe/park only).
- **Stadium exterior / stands / showers / recreation** — establishing
  shots and candid locker-adjacent moments.

Natural extensions (in neither list nor blueprints):

- **Hospital** (vs physio) — serious-injury escalation.
- **Away hotel** — `SceneInstance.hotel_away` exists, unused.
- **Agent's office** — distinct from the manager's office.
- **Childhood / family home** — backstory, the `FAMILY` role.
- **Taxonomy gap:** no `SceneType.SCHOOL`/`CAMPUS` despite a
  `LocationKind.SCHOOL` + authored school spec + school events.

## Consequences

- Players need no GPU/ComfyUI; visuals are instant, deterministic, QA-able.
- Larger download; fixed location/character set (acceptable per decision).
- Generative uniqueness becomes a dev-time authoring tool, not a runtime
  feature. If per-world bespoke art is later wanted, the hybrid (B) path
  remains reachable because the producer protocol and adoption pool are
  untouched.
- `IMPLEMENTATION_PLAN.md` gains a Phase 23 (Pre-baked rendering) once
  this design is accepted and the size question is answered.
