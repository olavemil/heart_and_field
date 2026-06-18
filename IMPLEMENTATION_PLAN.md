# Field & Heart — Implementation Plan

Source documents: `field_and_heart_design.docx`, `field_and_heart_technical.docx`.

## Guiding principle

Build the simulation engine as plain, testable Python in notebooks before any Ren'Py code exists. Ren'Py is a display shell — it calls the engine, never the other way around. Each phase below ends with something demonstrable in a notebook or, from Phase 6 onward, a running Ren'Py shell.

## Phase 0 — Project scaffold

- Create the directory layout from technical doc §2:
  - `game/engine/` (pure Python simulation)
  - `game/content/{events,templates,arcs}/` (authored data)
  - `game/scripts/` (Ren'Py `.rpy` labels, added in Phase 6)
  - `game/assets/` (added in Phase 7)
  - `notebooks/` (prototyping)
- Set up Python 3.11+ venv, install `numpy`, `pytest`. Defer `renpy`, `ollama`, `comfyui` clients until their phases.
- Add `pyproject.toml` or `requirements.txt`, a minimal `pytest` config, and `.gitignore` covering `generated/`, `__pycache__/`, `*.rpyc`.

**Exit criteria:** `pytest` runs green on an empty test suite; `python -c "from engine import characters"` imports cleanly.

## Phase 1 — Core data model (technical §3)

Implement as dataclasses. No behaviour yet beyond what the tuple/observable formulas require.

- `stats.py`: `StatName` (enum), `StatTuple` with `perceived()` and `acted_on()`, `ObservableName` (enum), `OBSERVABLE_FORMULAS` from design §2.4.
- `characters.py`: `TierACharacter`, `TierBCharacter`, `TierDSeed` + `project()`, `CharacterRole`, `Disposition`, `ROLE_WEIGHTS`, `DISPOSITION_WEIGHTS`.
- `relationships.py` (or inside `characters.py`): `RelationshipState`, `RelationshipDynamic`.
- `motivators.py`: `Motivator`, `MotivatorSource`, decay math.
- `outcomes.py`: `OutcomeRecord`, `WeekPhase`.

**Tests:** observable formulas return values in `[0,1]`; `StatTuple.perceived()` is noisier under low awareness; `TierDSeed.project()` respects role/disposition weighting.

**Exit criteria:** every dataclass round-trips through dict serialization (foundation for Phase 5 save system).

## Phase 2 — Phase simulation (technical §4)

- `simulation.py`: `simulate_phase`, `stat_composite`, `compute_synergy`, `check_goal`, `find_outliers`, `PhaseResult`.
- `self_evaluate()` implementing the awareness-noise / insecurity-amplified mood model.
- Sport-specific weight tables (`SPORT_WEIGHTS`); start with soccer and rugby.
- Fatigue accumulation across a match of N phases.

**Notebook deliverable:** `notebooks/02_phase_sim.ipynb` simulating a full 8-phase match between two rosters, plotting per-phase performance, momentum, and cumulative fatigue. Validate that:

- Mean performance ≈ composite over many runs.
- Low-awareness players show mood swings uncorrelated with actual performance.
- Late-game performance drops for low-stamina characters.

**Exit criteria:** distribution checks pass (notebook assertions); no Ren'Py yet.

## Phase 3 — Event skeleton (technical §5)

- `events.py`: `EventBlueprint`, `RoleSlot`, `SceneBlock`, `EventInstance`, `GameContext`, `GameState`.
- Selection pipeline: `check_prerequisites`, `can_cast`, `compute_weight`, `recency_penalty`, `select_event`.
- Outcome resolution without narration (just stat deltas + summary string).
- Minimal blueprint authoring format (YAML or Python dicts in `content/events/`) and a loader.

**Tests:** casting respects role filters and optional slots; prerequisite/unlock/disable graph walks correctly; weight selection is reproducible under a fixed seed.

**Exit criteria:** notebook can load ~10 authored blueprints and run a synthetic week of event selection producing outcome records.

## Phase 4 — Narrative templates (technical §6, design §7)

- `narrative.py`: `NarrativeTemplate`, `TemporalRef`, `NarrationContext`, `SLOT_RESOLVERS`, `fill_template`, `narrate` (LLM-off path only).
- Authored template loader from `content/templates/`.
- `resolve_outcome()` producing `arc_summary` via digest-append pattern; `compress_arc_summary` helper.
- Slot resolvers: `name`, `prior`, `trigger`, `arc`, `mood_descriptor`, `standout_action`.

**Exit criteria:** given a sequence of events, the engine produces coherent narration strings using templates only. Two independently authored events referencing `{prior}` read as connected.

## Phase 5 — Schedule, arcs, clocks, save (technical §5.3, §7, §8) ✅

- `schedule.py`: `WeekSchedule`, `EventSlot`, `BlockType`, skeleton generator, `force_next`.
- `arcs.py`: blueprint graph traversal, arc event detection (via `carries_arc_context`).
- Clock system: `Clock`, `ClockTick`, `tick_clocks`, integration into `compute_weight`.
- `save.py`: `serialise`/`deserialise` covering characters, outcomes, clocks, schedule, relationships.

**Exit criteria:** a multi-week headless simulation in a notebook runs drama → pregame → phases → postgame, with at least one clock reaching threshold and forcing an event. Save → load → resume produces identical continuation.

## Phase 6 — Ren'Py shell (technical §7.2) ✅

- Minimal `game_loop.rpy`, `drama_block.rpy`, `game_block.rpy`, `postgame_block.rpy`.
- Placeholder `ui_screens.rpy` for schedule overview and relationship panel.
- Engine instantiated once; Ren'Py labels call engine methods and display returned strings. No custom logic in `.rpy` files beyond flow control.
- Hook Ren'Py's save system to `engine.save.serialise/deserialise`.

**Exit criteria:** Ren'Py project runs end-to-end on text only (no sprites, default background). Player can play through a week, save, quit, reload.

> **Status correction (June 2026):** the "hook Ren'Py's save system" item never
> actually landed — what shipped was a parallel JSON stash in
> `persistent.fh_saves`, reachable only from the end-of-week menu, while
> Ren'Py's native save screens crashed on unpicklable store contents
> (label-body module imports; `session` holds blueprints with lambdas).
> Fixed in Phase 22A.

## Phase 7 — Visual prototype (technical §9) ✅

- `visual.py`: `CharacterVisual`, `Expression`, `Pose`, `TeamPalette`, `SpriteLayer`, `render()` dispatching to `_render_flat`.
- `EXPRESSION_OVERLAYS` + `apply_overlay` with disk cache.
- Face generation (`FaceGenerationSpec`, `generate_face`) via ComfyUI or SD API; cache to `generated/faces/` with fixed seeds.
- Tier D face pool (~20–30 images) keyed by `age_group × build × gender_presentation`.
- Background generator (`BACKGROUND_PROMPTS`, `get_background`) with prompt-hash cache.
- Ren'Py `show_character` / `set_background` labels wired to `CharacterVisual.render()`.
- **ComfyUI integration** (`comfyui.py`): REST client with txt2img + img2img workflows using Flux 2 Dev (fp8 mixed) + Mistral 3 Small text encoder + Turbo LoRA. Auto-disables after 3 consecutive errors. PIL placeholder fallback when ComfyUI is unavailable. Config serialised with save data. 28 tests covering workflow generation, prompt building, mock server integration, and fallback paths.
  - Models: `flux2_dev_fp8mixed.safetensors` (diffusion), `mistral_3_small_flux2_bf16.safetensors` (text encoder), `full_encoder_small_decoder.safetensors` (VAE), `Flux_2-Turbo-LoRA_comfyui.safetensors` (LoRA).
  - ComfyUI desktop app runs on port 8000 (not default 8188).

**Exit criteria:** every scene displays a generated background and character portrait with mood-appropriate tinting. Generation never blocks mid-scene (session-start warm-up or lazy-on-first-access).

## Phase 8 — LLM narration (technical §6.3) ✅

- `llm.py`: LM Studio client (OpenAI-compatible API), `build_llm_prompt`, `LLMClient.generate`, silent fallback to filled template. Uses `urllib` (stdlib) — no extra dependency.
- Per-event-type opt-in via `LLM_OPT_IN_TAGS` (conflict, vulnerability, postgame, romantic, celebration); low-drama events (training, downtime) stay template-only.
- Prompt includes arc summary, previous outcome, cast names, filled template, system prompt constraining "keep names and facts."
- `enhance_narration()` validates LLM output retains cast names — falls back if hallucinated.
- `narrate()` in `narrative.py` accepts `use_llm` + `llm_client` + `event_tags` params.
- `GameSession` stores `llm_client: LLMClient` and `use_llm: bool`, wired into `narrate_outcome()`.
- LLM config serialised/deserialised with save data.
- 21 new tests in `test_llm.py` (prompt building, opt-in logic, mock server integration, fallback paths, config roundtrip). Total: 203 tests, 0 failures.

**Exit criteria:** ✅ with LLM enabled, high-drama scenes read more varied than template-only; with LLM disabled or unavailable, game still plays identically using filled templates.

## Phase 9 — Content authoring ✅ (infrastructure + first pass)

- Event library covers design §8 categories: pregame, postgame, training, downtime, conflict, vulnerability, celebration, romantic, external-pressure, mentor/rival. Authored in `game/content/events/`.
- Template pools under `game/content/templates/`: each event category has a specific pool, with `generic.py` catching tail via tag match.
- `test_authored_templates_load_and_cover_blueprints` asserts every loaded blueprint has at least one matching template (id or tag).
- Arc chains wired through `carries_arc_context=True` on postgame loss silence, external contract talk, mentor quiet word, rival challenge, conflict blame→apology.

**Further work:** tune weights / clock thresholds from playtest; author remaining in-phase events (goal / near-miss / late-game surge) once phase-sim hooks exist.

## Phase 10 — Composite sprites ✅ (infrastructure)

- `CharacterVisual._render_composite` implemented: z-order sort, per-layer palette tinting (`_apply_layer_tint`), alpha composition, gentler emotion overlay on top.
- `SpriteLayer` extended with `expression`/`pose` filters, `tint_strength`, dict round-trip.
- `select_layers()` filters layers by expression + pose with NEUTRAL fallback so sprites never render blank.
- `procedural_layers()` builds a deterministic body/kit/hair/expression stack from `FaceGenerationSpec` + `TeamPalette`, letting the composite path run before authored art exists.
- `VisualManager.populate_procedural_layers()` opts named characters into the composite path without touching Ren'Py.

**Further work:** author real body/kit/hair/expression PNGs per named character; remove the flat prototype path once all Tier A + Tier B composites render as intended.

## Phase 10.5 — Background scene graphs ✅ (infrastructure)

- `background_pool.py`: `LocationDescriptor`, `SceneGraphSpec`, `BackgroundEntry`, `SceneGraphInstance`, `BackgroundManifest`. Graphs own claims; nodes attach lazily; visited entries persist, prefetched-unvisited entries detach to an adoption pool on `release_graph` / `reap_unvisited`.
- `background_generator.py`: `BackgroundGenerator.get_background(graph_id, node)` is the hot path (synchronous gen → mark visited → schedule neighbors). `ImageProducer` and `PrefetchScheduler` are protocols; `PlaceholderImageProducer` writes solid-colour PNGs; `Inline`/`Deferred`/`NoOp` schedulers cover test and runtime cases.
- Cold-start adoption: a fresh graph with no anchors can adopt a pool entry whose descriptor + node-name match. Warm graphs generate fresh from sibling anchors.
- `GameSession.init_backgrounds(assets_root)`, `resolve_scene(blueprint, cast)`, `scene_path(...)`, `release_scene(graph_id, *, close)`, `drain_background_prefetch(...)`. Authored `LocationCue` on `EventBlueprint` carries spec_id + node_name + optional graph_id (marquee) + descriptor_overrides (ad-hoc).
- Worked-example tags: `downtime.shared_meal` (player_home / kitchen), `vuln.injury_worry` and `mentor.quiet_word` (main_school / locker_bay), `vuln.post_loss_confession` (ad-hoc suburban_house / living_room with cold mood).
- Authored specs in `game/content/scenes/`: `suburban_house`, `school`. Ren'Py wiring in `game_loop.rpy` (boot-time init), `save_load.rpy` (re-init on load), `drama_block.rpy` / `postgame_block.rpy` (resolve scene → set background → release after narration → drain a couple of prefetch jobs).

**Further work:** real ImageProducer (SD3.5 + img2img on anchor) — placeholder still ships variants until then; manifest as part of save file (currently lives standalone on disk).

## Phase 11 — Background animation (addendum §1) ✅

Layered visual treatment on top of Phase 10.5's single-image scenes. Four independent layers (variant crossfade, noise overlays, time-of-day grade, mood grade) compose via Ren'Py ATL. Variation intent: subtle motion (light shifts, swaying foliage, candle flicker) — never camera-angle changes.

### 11A — Variant sets per node ✅

- Extend `BackgroundEntry.image_path: str` → `image_paths: list[str]` (primary at index 0, variants at 1..N). Manifest schema bumps; old entries reload as single-variant.
- `BackgroundGenerator._generate_fresh` produces only the primary by default; `generate_variant(graph_id, node_name)` appends an additional path using primary as img2img anchor + a variation prompt suffix (very low denoise so variants are near-identical to primary). Placeholder producer emits subtle hue shifts to exercise the pipeline before SD lands.
- **Promotion policy:** `SceneGraphInstance.visit_counts: dict[node_name, int]` increments on `mark_visited`. Visit count 2 schedules variant 2 (background); visit count 3 schedules variant 3; cap at 3.
- **Eager warmup for marquees known at game start:** at `init_backgrounds`, scan all blueprint `LocationCue`s for marquee `graph_id`s, create those graphs eagerly, and schedule full 3-variant generation for the entry node. Other rooms still lazy-attach on first visit.
- New session methods: `scene_variants(graph_id, node) → list[Path]` (for Ren'Py crossfade); `scene_path` continues to return the primary.
- Save round-trip preserves `image_paths` and `visit_counts`.
- Tests: variant generation, visit-driven promotion, marquee warmup, manifest persistence.

### 11B — Colour grades ✅

- New `engine/color_grades.py`: `TimeOfDay`, `Weather`, `SceneMood` enums + `ColorGrade` dataclass + the three lookup tables verbatim from addendum §1.3.
- `init_backgrounds` renders each grade as a solid-colour PNG into `game/assets/grades/` (deterministic, ~1KB each, cached on disk — regenerated only when the lookup table changes).
- **Atmosphere drivers:**
  - `time_of_day` advances per schedule slot (DAWN at slot 0, MORNING at 1, … wraps within a day).
  - `weather_tendency` drawn once per week at `start_week()`; per-day `weather` drawn from a biased distribution around the tendency (70% tendency, 30% drift to neighbours). Persisted on the schedule.
  - `mood` derived from `team_morale` + `momentum` via a small mapping table (e.g. high momentum + positive morale → EUPHORIC; bruising loss → MELANCHOLY; tight match → CHARGED).
- New `SceneAtmosphere` carrier; `session.atmosphere() → SceneAtmosphere`; `session.grade_paths() → tuple[Path, Path]` returns `(time_of_day_grade, mood_grade)`.
- Tests: PNG generation determinism, weather draw distribution under tendency, mood derivation table, atmosphere round-trip with save.

### 11C — Noise overlays ✅

- New `engine/overlays.py`: `NoiseOverlay`, `OverlayAnim` enums + `OverlaySpec` + `OVERLAY_SPECS` and `SCENE_OVERLAYS` tables.
- Bridge: thin `LocationKind → list[NoiseOverlay]` map (no full `SceneType` refactor; that's Phase 16). House → grain + dust; school → grain; gym → grain; pitch/stadium → grain + crowd; pool → grain + shimmer.
- Procedural overlay generation at `init_backgrounds`: PIL noise functions write `grain.png`, `dust.png`, `shimmer.png`, `rain.png`, `crowd.png` into `game/assets/overlays/` if missing. Deterministic seed per overlay so regen reproduces. Cached across sessions.
- Weather-conditional overlays merged at lookup time: rain weather adds `RAIN_STREAK` regardless of scene type; clear midday outdoor scenes add `HEAT_SHIMMER`.
- New `session.overlays_for(graph_id, node) → list[OverlaySpec]` returning the merged stack.
- Tests: spec registry, scene-kind mapping, weather merge, deterministic PNG generation, regen-on-missing.

### 11D — Ren'Py ATL composite ✅

- New `image scene_live` per addendum §1.4 — variant crossfade base + grain + per-scene overlays + time grade + mood grade.
- `drama_block.rpy` / `postgame_block.rpy` switch from `scene expression str(bg_path)` to:

  ```
  $ scene_info = session.resolve_scene(bp, cast)
  if scene_info is not None:
      $ session.set_active_scene(*scene_info)
      scene scene_live
  ```

  with `set_active_scene` storing variants + overlays + grades on a small `ActiveScene` struct that the ATL displayables read from.
- Crossfade timer (60–90 s) lives in ATL, not Python. Variant pointer cycles `image_paths[(i+1) % len(image_paths)]`.
- No automated tests — manual smoke checklist:
  1. Boot a new game; status bar reads "Week 1 · Mon · Morning · 08:00".
  2. Visit `downtime.shared_meal` (player_home/kitchen) — kitchen background composites with grain + dust overlays + morning grade + mood grade.
  3. Skip ahead to Tuesday training — clock fast-forwards to "Tue · Midday · 12:00", grade swaps from morning to midday tint.
  4. Force a rainy week (set `schedule.daily_weathers["sat"] = "rain"`) — match-day shows the rain streak overlay over the stadium, weather grade reads cool/blue.
  5. Run the match — status bar swaps to "Match vs Northgate" for the duration; afterward reads "Sat · Evening · 20:00".
  6. Save / load mid-week — clock and current_location restore correctly; grades and overlays regenerate from cached PNGs.

**Exit criteria:** background animation visibly conveys time-of-day, weather, and mood without regenerating images mid-scene; variant crossfade reads as breathing motion (not a hard cut to a different shot); marquee scenes pre-warm at game start, ad-hoc scenes promote on revisit.

**Deferred from this phase:**

- Real img2img variants (still placeholder until SD pipeline lands)
- `SceneType` / `SceneInstance` enum + global `SCENE_ADJACENCY` (Phase 16)
- Camera-angle variants and parallax depth (separate feature)

## Phase 11.5 — World clock + slot grid (refactor) ✅

Replaces the flat 14-slot `WeekSchedule` with a day-grid plus an
hour-precision world clock. Splits 11B's atmosphere derivation away
from `BlockType` so time-of-day is real clock time, not a per-slot
constant. Lands the status-bar surface that 11D's overlay reads.

### Model

- **Slots stay as spawn windows**, four per day with fixed anchors:
  morning 08:00, midday 12:00, afternoon 16:00, evening 20:00. Each
  slot is a 4-hour window. Night (00–08) is auto-skipped.
- **One slot per day is "anchored"** (training, match, etc.); others
  are free for drama/social/downtime events.
- **`WorldClock(week, weekday, hour, minute)`** advances continuously.
  Drives time-of-day, weather, and the status bar.
- **Match block** consumes the entire afternoon (16:00→20:00) regardless
  of phase count — covers movement, prep, pre/post events. Status bar
  shows "Match vs <team>" rather than the clock during the block.
- **Outcome-driven durations:** `BranchOutcome.duration_minutes` is the
  authoritative time cost. The same player choice ("join their table")
  may resolve to different outcomes ("ate with friends" vs "ate alone
  after social check failed"); the *outcome* drives the duration.
- **Movement costs:** 5 min within a graph (room to room), 30 min
  between graphs (home→school). Auto-teleport (free, instant) when
  the move is part of crossing into a new slot's anchor — i.e. the
  character "shows up" for appointments.
- **Slot fast-forward:** when an event ends and there's not enough
  time before the next slot for another event, the clock jumps to the
  next slot's anchor and the status bar flags the transition.

### 11.5A — Parallel clock (no schedule grid yet) ✅

Smallest landable step. Adds the clock to state without restructuring
the schedule. Atmosphere reads from clock instead of block type.

- New `engine/clock.py`: `Weekday`, `Slot`, `WorldClock`, `SLOT_START_HOUR`
  (8/12/16/20), `clock_to_slot()`, `time_of_day_for_hour()`.
- `GameState.clock: WorldClock` — initialised to `(week=1, MON, 8, 0)` for
  new games; reset to Monday 08:00 in `start_week`.
- Refactor `engine/color_grades.py` to drop `BLOCK_TIME_OF_DAY`; keep
  the lookup tables. Add `time_of_day_for_hour(hour)`.
- Refactor `session.atmosphere()` — drops the `slot_index` arg, reads
  `state.clock` directly. Weather still per-slot for 11.5A; per-day in
  11.5B.
- New `session.clock_display() → ClockDisplay` dataclass with `week`,
  `weekday`, `slot`, `hour_minute`, `next_slot_in_minutes`,
  `transition_warning: bool`, `match_label: str | None`.
- `WorldClock` round-trips in save (`save.py` update).
- Tests: clock arithmetic, slot mapping, atmosphere reads clock,
  status-bar surface, save round-trip. Existing 11B tests reshape to
  drop slot_index argument.

### 11.5B — Schedule grid + event durations ⚠️ partial

> **Status correction (June 2026):** previously marked ✅, but only the
> duration half landed (`duration_minutes` on blueprint/branch, clock
> advance, per-day weather). The grid restructure did **not**: there is no
> `DaySchedule`, `WeekSchedule.slots` is still the flat list, `slot_affinity`
> was never built (`BLOCK_TAGS` still routes — see Phase 22B), and
> `game_loop.rpy` still iterates slots. Remaining work folds into a future
> schedule-grid pass if still wanted; the flat list is currently canonical.

Replaces the flat slot list with a day-grid; introduces durations.

- `engine/schedule.py`: `DaySchedule(weekday, weather, slot_events:
  dict[Slot, EventSlot | None])`. `WeekSchedule.days: list[DaySchedule]`.
  `WeekSchedule.slots` removed (or aliased for compatibility).
- `EventBlueprint.duration_minutes: int | None = None` (default 60).
  `BranchOutcome.duration_minutes: int | None` overrides per branch.
- `session.resolve_event()` advances clock by the resolved branch's
  duration; clamps to the slot window when overflow looms (fast-forward
  cue).
- Match anchor: matchday's afternoon slot consumes 16:00→20:00 as one
  block; the 8 phases happen within. Status bar swaps to match label
  during this block.
- Weather draw moves from per-slot to per-day; match-day's weather is
  the day's draw, shared by all phases.
- `BLOCK_TAGS` routing partially replaced by `slot_affinity` per
  blueprint. Existing authored events tagged with appropriate affinity.
- `game_loop.rpy` migrates from slot-iteration to day-grid iteration.
- Tests: durations advance clock, outcome-level overrides, match block
  consumes 4h, fast-forward when overflow, weather per-day, schedule
  grid persistence.

### 11.5C — Movement costs ✅

Tracks current location and charges movement on event resolution.

- `GameState.current_location: tuple[graph_id, node_name] | None`.
- `session.resolve_scene()` computes movement cost from
  `current_location` to the cue's resolved location:
  - same graph, same node → 0 min
  - same graph, different node → 5 min
  - different graph → 30 min
  - auto-teleport (free) when crossing into a new slot's anchored event.
- Movement cost added to clock advance during `resolve_event`.
- After resolution, `current_location` updates to the cue's location.
- Tests: cost matrix, auto-teleport at slot anchors, current-location
  persistence.

**Exit criteria (11.5 complete):** Status bar reads "Week 3 · Tuesday ·
Afternoon · 17:30" (or "Match vs Northgate" during a match block);
events advance the clock by outcome-specific durations; movement
between scenes consumes time correctly; the 4-hour slot model works
for both anchored (training/match) and free (drama/downtime) days.

## Phase 12 — Quirks (addendum §2) ✅

Two-dimensional tags — ``(domain, pattern)`` — that drive stat tilts,
relationship affinity/friction, and event-weight bias through lookup
tables. No per-quirk authoring needed beyond picking the pair.

- New `engine/quirks.py`: `QuirkDomain` (PERFORMANCE / SOCIAL / EMOTIONAL / COGNITIVE / PHYSICAL), `QuirkPattern` (COMPULSIVE / AVOIDANT / SEEKING / REACTIVE / RIGID / PERFORMATIVE), `Quirk` dataclass (frozen, hashable), `QuirkVisibility` (VISIBLE / INFERABLE / HIDDEN), `QuirkReveal` (per-character visibility rules).
- Lookup tables (verbatim from addendum §2.3 plus author extensions):
  - `QUIRK_AFFINITIES` — quirk pairs that work well together.
  - `QUIRK_FRICTIONS` — quirk pairs that generate conflict.
  - `QUIRK_STAT_MODIFIERS` — additive deltas on character stats.
  - `QUIRK_EVENT_BIAS` — multiplicative weight tags per quirk.
- Helpers:
  - `has_affinity(a, b)` / `has_friction(a, b)` — undirected lookups.
  - `pairwise_affinity(qs_a, qs_b)` / `pairwise_friction(...)` — count of matches across two cast members.
  - `stat_modifier(quirk, stat)` / `total_stat_modifier(quirks, stat)` — character stat tilts.
  - `event_weight_multiplier(quirks, tags)` — single-character bias.
  - `cast_event_weight_multiplier(cast_quirks, tags)` — composes per-character bias with cast-level affinity/friction bumps.
  - `visible_to_observer(reveal, *, observer_familiarity, witnessed_event_tags)` — gates HIDDEN/INFERABLE quirks.
- Character integration: `quirks: list[Quirk]` on both `TierBCharacter` and `TierACharacter`; Tier A also has `quirk_reveals: dict[str, QuirkReveal]` for per-character visibility hooks. Both round-trip through `save.py`.
- 25 tests: dataclass equality / round-trip, affinity/friction symmetry, pairwise counts, visibility gating (familiarity threshold + event-tag triggers), stat-modifier lookup + stacking, event weight composition, friction/affinity boost on conflict/warm events, lookup-table integrity (every key/value in the four tables uses valid enum members).

**Further work:** author quirks on existing roster characters. Build a quirk-reveal flow (events that flip a HIDDEN reveal to VISIBLE).

**Selection wired:** `engine.events.select_event` now uses a deterministic ``representative_cast`` (first eligible character per role, sorted by id, no RNG) to feed `cast_event_weight_multiplier` into the per-blueprint weight. Pre-quirk rosters keep their distribution (empty quirk lists → multiplier 1.0). Three new selection-bias tests exercise the path: matching-tag boost, no-op without quirks, friction-pair boost on conflict events.

## Phase 13 — Secret aspects (addendum §3.1–§3.5, §3.8) ✅

Structural pass on the secret system: full aspect taxonomy, membership
roles, four-band exposure narration, observer-perspective reveal that
mirrors Phase 12's quirk reveal API. LLM pipeline (mechanical →
description → aspect_phrases) lands in Phase 14; placeholder
characters in Phase 15.

- New `engine/secrets.py`. Top-level enums:
  - `SecretCategory` (AGENDA / TABOO / CONNECTION / HISTORY / IDENTITY)
  - `SecretRole` (OWNER / PARTICIPANT / WITNESS / SUSPECT)
  - `SecretRelationType` (SHARED / OPPOSING / DEPENDENT / AWARE_OF)
  - `ExposureBand` (HIDDEN / GLIMPSED / SUSPECTED / KNOWN) with `exposure_band(float)` projection (0.2 / 0.5 / 0.8 cutpoints, clamped)
  - `AspectType` (RELATIONSHIP / AGENDA / TABOO / HISTORY / IDENTITY)
- Aspect-specific enums: `RelationType`, `AgendaGoal`, `AgendaMethod`, `TabooSubject`, `TabooOrigin`, `HistoryEventType` — verbatim from addendum §3.3.
- Aspect dataclasses: `RelationshipAspect`, `AgendaAspect`, `TabooAspect`, `HistoryAspect`, `IdentityAspect`. Each carries an explicit `type` field; `aspect_from_dict(d)` polymorphic dispatcher reads the discriminator. `SecretAspect` is a `Union` alias.
- `SecretMembership` (character_id, role, exposure, knows_other_members), `SecretRelation` (cross-secret link), `AspectPhrases` (one authored line per band, `by_band(band)` lookup).
- `Secret` (id, category, aspects, memberships, related_secrets, arc/event hooks, exposure_level, reveal_triggers, reveal_threshold, mechanical/description/aspect_phrases, optional `meta_secret`). `__post_init__` enforces the addendum's "one layer deep" rule on `MetaSecret`.
- **Reveal symmetry with quirks** — `aspect_band_for_observer(secret, aspect_id, *, observer_id, observer_familiarity, witnessed_event_tags)` accepts the same observer-side inputs as `engine.quirks.visible_to_observer` but returns an `ExposureBand` because secrets carry four bands. Members read at their `membership.exposure`; non-members start at `secret.exposure_level` and get a one-band bump (capped at SUSPECTED) when a witnessed event matches `reveal_triggers` or familiarity crosses `reveal_threshold`. `aspect_phrase_for_observer` and `secret_visible_to(...)` compose this with the authored phrase pool.
- `GameState.secrets: dict[str, Secret]` is the world-level registry; round-trips through `save.py` (omitted older saves default to empty).
- 33 tests in `tests/test_secrets.py` — exposure-band thresholds (and clamping), `AspectPhrases.by_band`, all five aspect dataclasses round-trip via `aspect_from_dict`, `Secret.membership_for` / `aspect_for`, full secret persistence, MetaSecret round-trip + invalid-state validation, observer reveal (member exposure, non-member default, tag-trigger bump, familiarity bump, SUSPECTED cap, unrelated tag no-op), phrase lookup edge cases (HIDDEN → None, missing aspect → None, missing phrases → None). Plus a save-level round-trip test in `tests/test_save.py`.

**Further work:**

- Wire secret-driven event gating into `select_event` (analogue of quirk bias) once `requires_aspects` / `boosted_by_aspects` / `requires_secret_role` move from `EventBlueprint` design (addendum §3.8) into the actual blueprint dataclass.

## Phase 14 — Secret LLM pipeline (addendum §3.6) ✅

Four bounded calls (one deterministic templating, three LLM) turn a
structured secret into authored band narration. Pipeline runs once per
secret at character / world initialisation; results cache on the
``Secret`` so play never blocks on the LLM.

- New `engine/secret_llm.py`:
  - `compose_mechanical_description(secret, cast)` — deterministic, no LLM. Five templates (one per AspectType). Renders every aspect to a sentence and joins with `.`. Holder name resolved via `primary_holder()` (OWNER → PARTICIPANT → WITNESS → SUSPECT priority). Unmapped character ids fall through as the id itself so missing placeholder bindings show up in dev.
  - `flavor_secret(client, secret, *, cast, character_label)` — LLM call 1. Uses `LLMPrompt`/`LLMClient` from Phase 8. Falls back to the mechanical sentence on any failure (disabled, error, empty response).
  - `generate_aspect_phrases(client, aspect, *, mechanical, description)` — LLM call 2 (one per aspect). Asks for strict JSON with the four band keys; rejects malformed JSON, non-string values, and empty values. Falls back to a deterministic phrase set that escalates the mechanical sentence across the four bands so reveal logic still has *something* at every band even with the LLM offline.
  - `reformulate_secret(client, description, aspect_phrases, mechanical)` — LLM call 3, optional consistency pass. Returns the input unchanged on failure. `needs_consistency_pass(secret)` heuristic triggers it on 3+ aspects.
  - `initialise_secret(secret, *, cast, character_label, llm_client, run_consistency_pass=None)` orchestrates the pipeline, mutating the secret in place and returning it. `run_consistency_pass` defaults to the heuristic; explicit `True`/`False` overrides.
- Every step degrades gracefully — a fully-disabled `LLMClient` produces a working secret with mechanical + deterministic-fallback band phrases.
- 34 tests in `tests/test_secret_llm.py` covering: every aspect type's template (relationship, agenda with target inlining, taboo, history with multi-shared rendering, identity), holder priority, unmapped-id passthrough, multi-aspect joining; flavor with clean / disabled / empty / pre-set-mechanical paths; aspect phrases with clean JSON / disabled / invalid JSON / missing keys / empty values + JSON parsing edge cases; reformulate pass-through; consistency-pass heuristic; full orchestration with 2-aspect (no reformulate) / 3-aspect (with reformulate) / explicit-skip / pure-fallback flows. Each path verified through deterministic mock clients — no real LLM hits in the suite.

## Phase 15 — Character placeholders (addendum §3.7) ✅

Stable-id placeholders let secrets reference characters who don't yet
exist in the cast. The placeholder id is fixed from the moment the
secret is composed; aspects keep referencing it. When the placeholder
is resolved, a real ``TierBCharacter`` takes the same id, so every
existing aspect reference works without rewriting.

- New `engine/placeholders.py`:
  - `CharacterPlaceholder(id, required_role, required_relation, scheduling_priority, introduction_event_tags, secret_ids, suggested_name)` — full data model with optional fields for everything except the stable id and required role.
  - `placeholder_ids_in_secret(secret)` — discovers every character id referenced by a secret's aspects (relationship target, history shared_with / known_to, agenda target).
  - `unresolved_references(state)` — maps `placeholder_id → {secret_ids}` for ids that aren't yet bound to a real character. Authors can use this to spot dangling references.
  - `resolve_placeholder(state, placeholder_id, *, name=None, character_factory=None)` — generates a real `TierBCharacter` reusing the placeholder id, registers it in `state.characters`, and removes the placeholder. Optional `character_factory` hook lets future random-character generators plug in without changing the call site.
  - `due_placeholders(state, *, witnessed_event_tags)` — placeholders ready to introduce, filtered by event-tag overlap (or flexible if no tags authored), ordered by `scheduling_priority` descending.
- `GameState.placeholders: dict[str, CharacterPlaceholder]` round-trips through `save.py`. Legacy saves without the field deserialise to an empty dict.
- 20 tests in `tests/test_placeholders.py`: dataclass round-trip (full and minimal), reference discovery for every aspect type, `unresolved_references` filtering, full resolution lifecycle (id reuse, name resolution, factory hook, error paths for unknown id and id collision), scheduling under various tag overlaps and priority orders, save round-trip + legacy compatibility.

## Phase 16 — Scene taxonomy (addendum §4.1–§4.2) ✅

Three-layer scene hierarchy authored alongside the existing visual
``LocationKind`` so narrative content can target richer scene labels
without breaking the background pipeline.

- New `engine/scene_taxonomy.py`:
  - `SceneCategory` enum (SPORT / SOCIAL / PRIVATE / TRANSIT / MEDIA / INSTITUTIONAL).
  - `SceneType` enum — verbatim from addendum §4.1, 32 entries spanning all six categories.
  - `SceneInstance` enum — styled variants (`BAR_LOCAL`, `BAR_UPSCALE`, `APARTMENT_SHARED`, …) keyed back to their parent type via `SCENE_INSTANCE_TYPE`.
  - `SCENE_CATEGORY` lookup, `category_for_scene_type()`, `instances_of(scene_type)`.
  - `SCENE_ADJACENCY` — undirected graph built from the addendum's directed edges, mirrored at module import. `neighbors(scene_type)` returns a frozenset.
  - **Bridge**: `scene_type_for_location_kind(LocationKind)` and `location_kind_for_scene_type(SceneType)` — best-effort mappings between visual and narrative taxonomies. Transit types have no LocationKind yet (return `None`); institutional/media types fall through to the school visual placeholder.
- 17 tests: enum coverage (every type has a category, every instance has a parent type), instance helpers, adjacency symmetry + authored-edge spot checks, isolated-type empty neighbours, frozenset return type, every `LocationKind` resolves through the bridge, round-trip stability, transit/press-room edge cases.

## Phase 17 — Event dimensions, chains, and gating wired (addendum §4.3–§4.6) ✅

Three independent enums compose every event id; an authored
"valid combinations" registry keeps the blueprint catalogue grounded;
chain edges declare how events follow each other along a shared
dimension; and the new `EventBlueprint` fields are wired all the way
through `select_event` and `resolve_outcome` so secrets and
placeholders actually shift play.

- New `engine/event_taxonomy.py`:
  - `EventNature` (12 actions), `EventDomain` (5 domains), `EventTone` (8 tones).
  - `EventId` frozen dataclass with `key()` (`{domain}_{nature}_{tone}`), `to_dict`/`from_dict`, and `from_key(string)` parser.
  - `VALID_EVENT_COMBINATIONS` — authored frozenset of every combo blueprints may use (~50 entries spanning addendum §4.4); `is_valid_event_id(eid)` predicate.
  - `ChainDimension` enum (SCENE / NATURE / DOMAIN / ADJACENT) and `EventChainEdge(from_id, to_id, dimension, condition)` dataclass with round-trip.
  - `CHAIN_EDGES` representative table from addendum §4.5; `chains_from(event_id, dimensions=...)` filtered lookup.
- `EventBlueprint` extended with the addendum §4.6 surface (defaults preserve back-compat):
  - `event_id`, `chain_edges`
  - `boosted_by_quirks`, `penalised_by_quirks`
  - `requires_aspects`, `boosted_by_aspects`, `requires_secret_role`, `reveals_exposure`
  - `valid_scene_types`, `preferred_instances`
  - `introduces_placeholders` (list of placeholder ids)
- **Wiring**:
  - `select_event` now drops blueprints failing `meets_secret_requirements(...)` (an aspect-type / secret-role gate against a representative cast).
  - `compute_weight` multiplies in `_aspect_boost_multiplier(...)` so `boosted_by_aspects` actually shifts selection (×1.25 per matching aspect type, multiplicatively stacked).
  - `resolve_outcome` calls `_advance_secret_exposure(...)` (bumps `secret.exposure_level` for cast-member secrets whose `reveal_triggers` overlap the event's tags, capped at 1.0) and `_introduce_placeholders(...)` (resolves listed placeholder ids via the Phase 15 helper, swallowing errors so a content typo can't crash play).
- 50 tests: `engine/event_taxonomy` (15 — `EventId` round-trip incl. key parser, `VALID_EVENT_COMBINATIONS` coverage and uniqueness, chain edge persistence + endpoint validity + dimension filter), `engine/scene_taxonomy` (17), `engine/events` wiring (18 — eligibility gates with and without matching secrets, `requires_secret_role` blocking and passing, `boosted_by_aspects` shifting selection over many trials, `reveals_exposure` advancing only on tag-trigger overlap and only for cast-member secrets, exposure capping at 1.0, placeholder introduction including silent skip on missing/already-resolved ids).

**Further work:**

- Compose chain edges into the actual selection pipeline (currently `chain_edges` data exists on blueprints but selection doesn't yet prefer chained follow-ups). Likely a separate "chain bias" multiplier on `compute_weight` keyed off the most recent outcome.
- Author content blueprints against the `EventId` triple — replace ad-hoc string ids in `game/content/events/` with `event_id=EventId(...)` once content authoring resumes.
- Hook `valid_scene_types` / `preferred_instances` into `LocationCue` resolution so events declaring scene preferences get matched to graphs of the right kind.

## Phase 18 — World genesis

The pipeline that takes a single seed and produces a playable world:
named main character, supporting cast, opponent seeds, a secret web,
and the first week's schedule. Wraps every system Phases 11–17 built
into one deterministic call so a new game starts varied and grounded.

### 18A — Random character generator

Pure-Python factory for one character at a time. No LLM, no visual
generation — just structured data fed by an injected ``random.Random``
so every roll is reproducible from a seed.

- New `engine/character_factory.py`:
  - Name pools (first / last) with optional gender bias; helper
    `generate_name(rng, *, gender_presentation=None)`.
  - Per-role stat profiles (`ROLE_STAT_PROFILES`) — striker leans on
    speed/finesse/confidence, defender on strength/cautiousness, etc.
  - `random_stats_flat(role, rng, *, variance)` for Tier B and
    `random_stats_tuple(role, rng, ...)` for Tier A (value +
    awareness + focus per stat).
  - `random_quirks(rng, *, count_range, role=None)` — 1–3 quirks
    drawn from `(QuirkDomain, QuirkPattern)` with optional
    role-aware weighting (strikers more likely PERFORMATIVE, etc.).
  - `random_descriptor(rng)` for visual `CharacterDescriptor`.
  - `generate_character(role, rng, *, tier, ...)` that composes the
    above into a `TierACharacter` or `TierBCharacter`.
- Tests: determinism under fixed seed, stat means converge to role
  profile over many trials, quirks are valid pairs, descriptor axes
  cover the full enum range, generated character round-trips through
  `save.py`.

### 18B — Roster + opponent seed builder

- New `engine/roster_factory.py`:
  - `default_squad_composition()` — sport-aware role distribution
    (soccer: 1 GK, 4 DEF, 4 MID, 2 FWD by default + bench).
  - `generate_roster(rng, *, composition, with_player=True)` produces
    a roster of TierB teammates plus optional Tier A player.
  - `generate_coaching_staff(rng)` — a manager and a physio.
  - `generate_opponent_seed(rng, *, opponent_rating, count)` —
    `TierDSeed` list with a club name pool.
- Tests: deterministic from seed, role distribution matches
  composition, generated rosters cast existing blueprints (smoke).

### 18C — Secret web generator ✅

- New `engine/world_genesis.py`:
  - `generate_secret_web(rng, *, characters, secret_count_range, llm_client, character_label)` —
    draws N secrets (N ∈ `secret_count_range`) across the five `SecretCategory` values.
    Per-category generators (`_generate_connection_secret`, `_generate_agenda_secret`,
    `_generate_taboo_secret`, `_generate_history_secret`, `_generate_identity_secret`)
    produce aspects, memberships, and reveal triggers.
  - External-vs-internal relation classification (`_EXTERNAL_RELATIONS`, `_INTERNAL_RELATIONS`,
    `_MIXED_RELATIONS`) decides whether a relationship target comes from the cast or spawns a
    `CharacterPlaceholder`. `_RELATION_TO_ROLE` maps relation types to placeholder roles.
  - `_link_shared_character_secrets` wires `SecretRelation` cross-references between secrets
    sharing a character membership.
  - `_build_placeholders` creates `CharacterPlaceholder` entries for every aspect target not in
    the cast, tracking `secret_ids` and inferring `required_role` / `required_relation` from
    the aspect.
  - Owner spreading: `_pick_owner` prefers unused characters so secrets distribute across the
    cast rather than clustering.
  - Runs `engine.secret_llm.initialise_secret` on each generated secret (with the world's
    `LLMClient` if available; falls back to a disabled client producing deterministic
    mechanical descriptions and fallback phrases otherwise).
  - Returns `(dict[str, Secret], dict[str, CharacterPlaceholder])` ready for `GameState`.
  - Fix: `unresolved_references` in `placeholders.py` now also filters `state.placeholders`,
    matching its docstring intent ("neither in characters nor in placeholders is a content bug").
- 35 tests in `tests/test_world_genesis.py` covering: integration (returns dicts, count within
  range, every secret has membership + aspect, real character references, unresolved_references
  empty after bookkeeping, determinism, different seeds diverge, initialise_secret called once
  per secret with counting client, no-LLM fallback, placeholder secret_id tracking, owner
  spread), per-category generators (aspect types, external/internal relation paths, no-placeholder
  categories), cross-secret linking (shared character creates relations, no link without shared
  character), placeholder builder (unbound target creation, existing character skip), cast map,
  save round-trip (serialise/deserialise preserves secrets + placeholders, unresolved_references
  empty after round-trip), edge cases (single character cast, zero secrets, large secret count,
  all categories reachable over 50 seeds). Total: 747 tests, 0 failures.

### 18D — `GameSession.new_game()` integration ✅

- `new_game(player_name, *, seed, customisation, roster, sport, content_root)` now has two paths:
  - **Generated path** (default, `roster=None`): calls `generate_roster(rng, sport=sport)` to build
    the full squad (15 Tier B teammates + manager + physio + Tier A player), then
    `generate_secret_web(rng, characters=…)` to weave secrets across the cast. The player picks up
    any overrides from `PlayerCustomisation`.
  - **Legacy path** (`roster=dict`): caller provides handcrafted characters directly. No secrets
    generated. Player gets flat 0.5 stats. Existing test helpers continue to work unchanged.
- New `PlayerCustomisation` dataclass in `engine/session.py`: `name` (unused — `player_name` arg
  always wins), `role: CharacterRole | None`, `quirks: list[Quirk] | None`,
  `stats: dict[StatName, float] | None`. All optional — `None` means randomise.
- Ren'Py `game_loop.rpy` start label rewritten: name input via `renpy.input`, role menu
  (Striker/Midfielder/Defender/Goalkeeper), `PlayerCustomisation` wired through
  `GameSession.new_game(…)`. Hardcoded roster removed entirely.
- 21 tests in `tests/test_new_game_integration.py`:
  - Generated path: player is Tier A with given name, full squad (≥10 chars), coaching staff
    present, secrets generated with mechanical descriptions, `unresolved_references` empty, player
    has quirks and varied stats.
  - Legacy path: injected roster present, player has flat stats, no secrets.
  - Customisation: role override, quirks override, stats override, role override on legacy path,
    `player_name` always wins over `customisation.name`.
  - Determinism: same seed → identical world, different seed → different world.
  - Save round-trip: characters + secrets + placeholders preserved, player data preserved, secret
    mechanical descriptions preserved.
- Total: 768 tests, 0 failures.

**Exit criteria for Phase 18:** ✅ `GameSession.new_game("Alex", seed=42)` produces a
randomly-generated world with named teammates, coach, secret memberships across the squad,
and loads content for the first week — without any hardcoded character data in `.rpy` files.
Re-running with the same seed produces an identical world; running with a different seed
produces a meaningfully different one.

## Phase 19 — Content pass + chain bias ✅

- Migrate existing `game/content/events/*.py` blueprints to use
  `EventId` triples.
- Wire `chain_edges` into `compute_weight` (chain bias multiplier
  keyed off the most recent `OutcomeRecord.event_id`).
- Wire `valid_scene_types` / `preferred_instances` into
  `LocationCue` resolution.
- Author blueprints for each `VALID_EVENT_COMBINATIONS` triple
  missing today.

**Delivered (Phase 19):**

Engine wiring:

- `_chain_bias()` in `events.py` — reads the most recent `OutcomeRecord.taxonomy_id`,
  looks up outgoing `EventChainEdge`s via `chains_from()`, and boosts by `CHAIN_BIAS_BOOST`
  (1.8×) when the blueprint's `event_id` matches an edge's `to_id`. Integrated into
  `compute_weight()`.
- `OutcomeRecord.taxonomy_id` field added — set by `resolve_outcome()` from
  `blueprint.event_id`, serialised/deserialised, backward-compatible (defaults `None`).
- `_cue_from_scene_types()` in `session.py` — when a blueprint has `valid_scene_types`
  but no explicit `location`, synthesises an ad-hoc `LocationCue` by mapping scene types
  through `location_kind_for_scene_type()` and matching against loaded `SceneGraphSpec`s.
  Integrated into `resolve_scene()`.

Content:

- All 21 existing blueprints migrated to `EventId` triples with `valid_scene_types`,
  and strategic `boosted_by_aspects` / `reveals_exposure` fields populated.
- 35 new blueprints authored across 5 new content files (`sport.py`, `relationship.py`,
  `institutional.py`, `personal.py`, `secret.py`) — achieving 51/51 coverage of
  `VALID_EVENT_COMBINATIONS`.
- Secret-domain blueprints use `requires_aspects` and `requires_secret_role` gates.

Tests: 15 new tests in `test_phase19.py` (783 total, 0 failures).

> **Status correction (June 2026):** Phase 19 authored 35 new blueprints but
> skipped two follow-through steps, both surfacing as "hardcoded-feeling"
> play: (1) 9 blueprints carried tag sets unreachable through `BLOCK_TAGS`
> routing — fixed in Phase 22B; (2) no template pools were authored for the
> new categories, so 37 of 55 blueprints only match the 3 generic templates
> and roughly a third of narrations render as the raw one-line branch
> summary — Phase 22E.

## Phase 20 — League and progression ✅

Configurable league system: sport selection, league tier/format, season
structure with round-robin fixtures, standings table, and opponent
integration into the match flow.

### 20A — League config model ✅

- New `engine/league.py`:
  - `LeagueFormat` enum (`OPEN` / `CLOSED`) — open leagues have
    promotion/relegation narrative hooks; closed leagues don't.
  - `LeagueTier` enum (`PROFESSIONAL` / `SEMI_PRO` / `AMATEUR`) — shapes
    opponent skill range via `TIER_SKILL_RANGES` and narrative tone
    (sponsor pressure vs grassroots community).
  - `LeagueConfig` frozen dataclass: `club_name`, `opponent_count`,
    `league_format`, `tier`. Properties: `total_clubs`, `season_weeks`
    (= 2 × opponent_count for home+away round-robin). Round-trips via
    `to_dict` / `from_dict`.
  - `Fixture` dataclass: week, home/away clubs, goals, played flag.
    Helpers: `result_for(club)` → W/D/L, `goals_for/against`,
    `opponent_of`. Round-trips.
  - `LeagueStanding` dataclass: W/D/L/GF/GA with computed `points`
    (3 for win + 1 for draw), `goal_difference`, `sort_key`.
  - `Season` dataclass: config, opponent clubs, fixtures list,
    current_week pointer. Helpers: `fixture_for_week`, `current_fixture`,
    `standings()` (sorted table), `player_position()`,
    `record_result(week, home_goals, away_goals)`,
    `simulate_other_results(week, rng)` (Poisson model keyed off club
    skill rating with home advantage), `advance_week()`.
  - `generate_fixtures(club_names, rng)` — standard circle-method
    round-robin (home+away), shuffled for variety.
  - `generate_season(rng, config, clubs)` — composes fixture list from
    config + opponent clubs.
  - `OpponentClub` serialisation: `_opponent_club_to_dict` /
    `_opponent_club_from_dict` (deferred from Phase 18B review).

### 20B — GameState + save wiring ✅

- `GameState.season: Season | None` field added to `events.py`.
- `save.py` updated: serialises/deserialises season (backward-compatible —
  legacy saves without season load as `None`).

### 20C — Session integration ✅

- `new_game()` accepts `league_config: LeagueConfig | None` parameter.
  On the generated path (roster=None), generates opponent clubs via
  `generate_season_opponents()` with skill range from `TIER_SKILL_RANGES[tier]`,
  then builds a `Season` via `generate_season()`. Legacy path skips.
- `setup_match_from_season()` — pulls the current fixture from the season,
  resolves the opponent club, and calls `setup_match()` with the club's
  Tier D seeds and name. Falls back to generic opponent if no season loaded.
- `evaluate_match()` now calls `_record_match_in_season()` which records
  the player's result and simulates all other league fixtures for that week.
- `advance_week()` also advances `season.current_week`.

### 20D — Ren'Py flow ✅

- `game_loop.rpy` start label extended with:
  - Sport selection menu (Soccer/Rugby/Basketball).
  - League tier menu (Professional/Semi-Pro/Amateur).
  - League format menu (Open/Closed).
  - Club name input.
  - `LeagueConfig` wired through `GameSession.new_game()`.
- `game_loop.rpy` week_loop shows upcoming fixture and league position.
- `game_block.rpy` uses `setup_match_from_season()` instead of hardcoded
  opponent.

### Phase 18B fix (shipped with 20) ✅

- `_slug_id` suffix widened from 12-bit to 24-bit (collision-safe).
- `generate_roster()` enforces unique character IDs via set tracking +
  retry (up to 10 attempts). Staff generation inlined with same
  uniqueness check.

Tests: 59 new tests in `test_league.py` (842 total, 0 failures):

- `TestLeagueConfig`: 6 tests (defaults, properties, round-trip, tier
  skill ranges, pro>amateur ordering).
- `TestFixture`: 7 tests (W/D/L results, unplayed, uninvolved, goals,
  opponent_of, round-trip).
- `TestLeagueStanding`: 4 tests (points, GD, sort order, round-trip).
- `TestFixtureGeneration`: 7 tests (even/odd counts, pair completeness,
  12-team scale, single team, determinism, seed variation).
- `TestOpponentClubSerialisation`: 2 tests (round-trip, empty seeds).
- `TestSeason`: 14 tests (fixture count, club names, total weeks,
  current fixture, every-week coverage, empty standings, record result,
  standings after results, position, simulate others, advance, complete,
  lookup, determinism, seed divergence).
- `TestSeasonSerialisation`: 4 tests (empty round-trip, with results,
  save.py round-trip, legacy no-season).
- `TestHelpers`: 5 tests (mean skill, None/empty club, Poisson
  non-negative, Poisson mean convergence).
- `TestNewGameLeague`: 5 tests (creates season, custom config, legacy
  no season, determinism, tier skill impact).
- `TestSessionSeasonFlow`: 4 tests (setup from season, advance week,
  save round-trip, no-season fallback).

**Exit criteria:** ✅ `GameSession.new_game("Alex", seed=42, league_config=LeagueConfig(tier=LeagueTier.PROFESSIONAL))`
produces a 12-club league with round-robin fixtures, skill-appropriate opponents, and a
standings table. Match results flow into the table; other fixtures simulate automatically.
Ren'Py start flow lets the player choose sport, league tier, format, and club name.

## Phase 21 — Real visuals ✅

- `ComfyUIImageProducer` in `background_generator.py` — real `ImageProducer`
  backed by `ComfyUIClient`. Three generation paths:
  - **Fresh** (txt2img): first node in a graph, no anchor.
  - **Anchored** (img2img, denoise 0.65): subsequent nodes inherit palette/lighting
    from a sibling image.
  - **Variant** (img2img, denoise 0.35): subtle ambient shift for crossfade motion.
  - Falls back to `PlaceholderImageProducer` when ComfyUI returns `None`.
  - Node-level prompt hints (`_NODE_PROMPT_HINTS`) steer composition per room type.
  - Prompt built from `LocationDescriptor.to_prompt_fragment()` + node hint + prefix.
- `SceneInstance` → `LocationDescriptor` bridge in `scene_taxonomy.py`:
  - `descriptor_overrides_for_instance()` returns socioeconomic, mood, palette
    overrides per instance (e.g. `BAR_LOCAL` → modest/warm/dim pub vs
    `BAR_UPSCALE` → affluent/cold/cocktail bar).
  - All 13 `SceneInstance` values have authored overrides.
- `LocationCue.scene_instance` field added to `events.py`.
- `GameSession._descriptor_for()` merges instance overrides between base
  descriptor and per-event overrides (instance < explicit overrides priority).
- `GameSession.init_backgrounds()` accepts optional `comfyui_client` parameter;
  auto-selects `ComfyUIImageProducer` when client is available, falls back to
  placeholder otherwise.
- 18 new tests (12 in `test_comfyui_producer.py`, 6 in `test_scene_taxonomy.py`).
  860 total tests passing.

## Phase 22 — Presentation pass (engine → screen gap)

Audit findings (June 2026): the engine pipeline works headlessly — a
5-seed × 4-week simulation through the exact `game_loop.rpy` code path
selected and cast an event for every non-game slot (0% "the day passes
quietly" fallbacks) — but play still *feels* hardcoded because no prior
phase connected scene presentation, sprites, match narration, or native
saves to the screen. This phase closes that gap, easiest/most-broken
first.

### 22A — Save integrity ✅

- Ren'Py's native save menu crashed (`Could not pickle <module 'time'>`,
  `traceback.txt` May 7): label-body `python:` blocks bound modules into
  the pickled store, and `session` itself is unpicklable (blueprints
  carry lambda predicates/filters).
- New `scripts/runtime.rpy`: `FHRuntime` holder bound at init keeps the
  engine session (`fh.session`) and per-event scratch (`fh.bp`) out of
  Ren'Py's save store; all module imports moved to `init python`.
- Engine state rides native saves as a JSON string (`fh_save_blob`,
  a saved store variable) checkpointed at week start and after each
  resolved event / match. `after_load` rebuilds the session from the
  blob, re-inits backgrounds, and resumes via `week_resume` at the
  current slot. Saves made mid-event re-run that event from selection
  on load (acceptable: "resume at the start of the in-progress scene").
- Rollback disabled (`config.rollback_enabled = False`) — engine
  mutations are not rollback-aware, so rolling back only desynced the
  display from the simulation. Re-enabling needs engine-side snapshots
  (deferred).
- The legacy `persistent.fh_saves` path remains as the explicit
  end-of-week "Save and quit" flow, now writing the same serialise()
  payload.

### 22B — Event routing completeness ✅

- `BLOCK_TAGS` extended so every authored tag group routes to at least
  one block: DRAMA adds `social` / `secret` / `romantic` /
  `institutional` / `external_pressure` / `mentor` / `rival`; DOWNTIME
  adds `social` / `solo` / `romantic` / `celebration`; POSTGAME adds
  `celebration`. (This is the stopgap for 11.5B's unbuilt
  `slot_affinity`.)
- `ingame`-tagged blueprints (`celebration.goal_huddle`) are explicitly
  skipped by `blueprints_for_block` until match-phase hooks exist (22F).
- Regression test: every loaded blueprint without the `ingame` tag is
  reachable from at least one block type.

### 22C — Generalised choice menu ✅

- `fh_choose_branch()` (runtime.rpy) uses `renpy.display_menu`, handling
  any branch count. Replaces the hand-unrolled 1/2/3-option menus in
  `drama_block.rpy` / `postgame_block.rpy` that silently auto-picked the
  first branch at 4+ options.

### 22D — Scene presentation ⚠️ partial

Done:

- `GameSession.scene_intro(blueprint, cast)` — engine-built pre-choice
  scene setting (location cue + cast names + an `EventTone`-keyed
  atmosphere line from `_TONE_INTRO_LINES`). No per-blueprint authoring
  needed; neutral-tone solo scenes return `""` and the line is skipped.
  Replaces the `e "[block_label]"` placeholder in both event blocks.
- `GameSession.focal_character(cast)` — picks the non-player cast
  member a scene puts on screen (`_FOCAL_ROLE_PRIORITY`, then first
  non-player role). `drama_block` / `postgame_block` now call
  `show_character` with it and hide after narration — first time the
  sprite pipeline (Phases 7/10/21) renders during play.

Remaining:

- Real `ChoiceNode` option labels per blueprint — the menu still shows
  title-cased branch ids ("Escalate" / "Defuse"). Intros now give
  context, but labels should express intent. Authoring pass over all
  55 blueprints (~130 labels).
- Optional bespoke `SceneBlock.templates` intro text for marquee events
  where the generic intro reads thin.

### 22E — Template pools for Phase 19 categories ✅

- Five new pools under `game/content/templates/`: `sport.py`,
  `relationship.py`, `institutional.py`, `personal.py`, `secret.py` —
  35 templates mixing event_id-attached entries for the
  highest-frequency blueprints (tactical_disagreement, hard_tackle,
  cut_off, boundary_talk) with tag-attached entries (`training`,
  `status`, `social`, `romantic`, `institutional`, `external_pressure`,
  `solo`, `secret`) for the tail. Tag-attached templates only use
  `{name}` / `{summary}` / `{mood_descriptor}` / `{arc}` slots since
  role names vary per blueprint; mood-gated variants split valence via
  `context_requirements`.
- Generic-only blueprint count: 37 → **0** (regression test
  `test_no_blueprint_is_generic_only`).

### 22F — Match narration ✅

- `narrate_match_phase()` in `narrative.py`: goal lines naming the
  scorer, balance-of-play lines (dominating / under pressure / even via
  `PHASE_GAP_THRESHOLD`), late-game surge/fade variants keyed off
  momentum. `GameSession.narrate_match_phase` resolves scorer +
  opponent names. Replaces the debug stat readout in `game_block.rpy`.
- `self_evaluation_line()` replaces the "perceived performance: 72%"
  readout — banded, awareness-filtered, can contradict the scoreline
  by design.

#### In-phase playable beats ✅

- `cast_event(..., pinned=...)` in `events.py` forces specific
  characters into roles (the real goal-scorer into `scorer`); a pinned
  character must still satisfy the slot filter.
- `GameSession.select_match_event` / `cast_match_event` /
  `resolve_match_event`: a teammate goal opens a playable beat
  (gated by `MATCH_EVENT_GOAL_CHANCE = 0.6`), weight-sampled from the
  `ingame` pool through the normal prereq/recency machinery. Resolution
  applies effects + logs the record but marks no schedule slot and
  advances no clock — the match block owns the whole afternoon.
- `game_block.rpy` calls `select_match_event` after each phase line;
  on a hit it runs a `match_event` sub-label (scorer on screen → choice
  → narration). `celebration.goal_huddle` is the first such event.
- Headless: ~60% of teammate goals fire a beat over 20 matches, 0
  crashes. Tests in `test_session.py::TestInPhaseMatchEvents`.
- Known pre-existing bug (flagged separately, not 22F): the match sim
  draws the scorer from `roster_players()` which includes staff, so a
  manager/physio can occasionally be named scorer (cast then fails
  gracefully). Fix is to filter to the playing squad before
  `simulate_phase`.
- Deferred: the player-scored beat (player mobbed by teammates) and
  near-miss / late-surge interactive moments — only `goal_huddle`
  is authored so far.

### 22G — Ren'Py lint gate ✅

- `scripts/check.sh` runs pytest + `renpy.sh lint` (falls back to the
  main checkout's SDK/venv when run from a worktree). Both stale error
  logs (`errors.txt`, `traceback.txt`) were `.rpy` regressions pytest
  cannot see — run this before committing changes under `game/scripts/`.

### 22H — LLM genre grounding ✅

- Diagnosis: with LM Studio live, opt-in events were enhanced by
  `llama-3.2-1b-instruct`, which drifted genre — a locker-bay injury
  scene came back set in a "dimly lit tavern". The text appears nowhere
  in authored content; the only output validation (cast names retained)
  passed, so the hallucination shipped to screen.
- `SYSTEM_PROMPT` now pins the world ("present day — training grounds,
  locker rooms…") and forbids setting changes / fantasy-period imagery.
- `build_llm_prompt` / `enhance_narration` / `narrate` gained a
  `location` parameter; `narrate_outcome` passes the blueprint's
  location-cue node so the prompt carries "Setting: locker bay". A/B
  against the live model confirms the drift disappears.
- Known limitation: prose quality is bounded by the 1B default model
  (`DEFAULT_MODEL` in `llm.py`); pointing the client at a larger loaded
  model (e.g. qwen3.6-27b) is a config change, not a code change.

### 22I — Launcher ✅

- `play.command` at repo root: double-clickable in Finder (macOS) and
  runnable as `./play.command`. Resolves the SDK at
  `./renpy-8.5.2-sdk`, honours `RENPY_SDK`, and falls back to the main
  checkout when run from a worktree.

### 22D (cont.) — ChoiceNode labels ✅

- Authored intent-voiced `ChoiceNode` options + prompts on every
  multi-branch blueprint (~40 blueprints) via parallel haiku subagents,
  file-disjoint. The branch menu now reads "Say it to his face" /
  "Let it go" instead of title-cased branch ids.
- New `tests/test_content_choices.py`: every ≥2-branch blueprint has a
  ChoiceNode, option keys match outcome keys exactly, no empty/id-echo
  labels.

### 22J — Gender-aware narration ✅

Playtest finding: the player always read as male regardless of chosen
presentation. Two surfaces leaked it — authored templates and branch
summaries both hardcoded "he/his/him" — and the LLM had no gender
signal so it guessed from names.

- **Pronoun resolvers** in `narrative.py`: `{they}` / `{them}` /
  `{their}` / `{theirs}` / `{themself}` (+ capitalised forms), role-
  scoped like `{they:player}` / `{their:mentor}`. Each reads the focal
  character's `gender_presentation`; androgynous → singular "they".
  Registered in `SLOT_RESOLVERS`.
- **`{summary}` now resolves recursively** — `_resolve_branch_summary`
  runs the summary back through `_substitute` (guarded against
  self-recursion) so summaries can carry pronoun slots too. The
  no-template fallback path uses it as well.
- **Templates rewritten** — all 46 hardcoded pronouns across 8 template
  files replaced with role-scoped slots, dodging the "they was" verb-
  agreement trap.
- **Branch summaries rewritten** — 142 hardcoded pronouns / gendered
  nouns across 15 event files converted to slots (or neutralised:
  "the older man" → "the senior pro" / `{name:mentor}`), via four
  parallel haiku subagents. A follow-up pass fixed second-person voice
  ("you") and verb-agreement breaks the agents introduced.
- **LLM gender grounding** — `build_llm_prompt` takes `cast_pronouns`
  and labels the cast line ("Alex (she/her)"); system prompt rule 5
  enforces it. Output is run through `_strip_pronoun_labels` since
  small models sometimes echo the "(she/her)" hint into prose.
- **Validator** `scripts/check_summary_pronouns.py` (+ regression test):
  flags bare gendered words, second person, verb-agreement breaks, and
  unresolved slots across all three genders. Run it after editing
  summaries.

### 22D (cont.) — Scene-intro LLM enhancement ✅

- `scene_intro` split into deterministic `_assemble_scene_intro`
  (testable) + an LLM rephrase pass grounded with location + cast
  pronouns, so repeated tones read fresh. Tone-line pools expanded
  (4 per tone, NEUTRAL added). LLM output trimmed to the last complete
  sentence (tight token cap was truncating mid-sentence).

### 22H — LLM model default ✅

- `DEFAULT_MODEL` → `liquid/lfm2-24b-a2b`, auditioned against the live
  LM Studio pool: fast (~1s warm), non-reasoning, stays on-genre.
  `_strip_reasoning` drops any `<think>…</think>` blocks reasoning
  models leave in content (unterminated → empty → template fallback).

Also fixed with 22A–C: stale `test_visual.py` placeholder-face size
assertion (256 → 512, left behind by the Phase 21 face-size bump).

## Phase 23 — Pre-baked rendering ✅ (largely shipped)

Build-time background pre-bake replaces runtime on-demand SD. Alternates
model (`SceneGraphSpec.alternates`, distinct shots per visit);
`PrebakedImageProducer` + `init_backgrounds(prebaked=True)` +
`NoOpPrefetchScheduler`; `scripts/prebake_assets.py` idempotent driver;
hot-tier + gap specs baked (74 shots). Runtime wired (prebaked
`resolve_scene` redirects every cue to the canonical `spec_id` graph).
New `LocationKind`s: TEAM_HQ, TRAINING_GROUND, BAR, MEDIA, TRANSIT. Locked
painterly recipe in `ComfyUIImageProducer`. Design:
`field_and_heart_prebake_rendering.md`. Figure assets
(`field_and_heart_figure_assets.md`) follow.

## Phase 24 — Narrative flow ✅

The pass that makes the LLM's individually-good fragments read as a
flowing scene with meaningful choices. Source: `narrative_adjustments.md`.
Landed branch `claude/crazy-proskuriakova-b6a142`, commits a8544ef→c8aa62f.

**Guiding distinction — two continuity tracks, tracked + stored
separately, never conflated:**

- **Journal** = *temporal* continuity ("what just happened / earlier
  today").
- **Arc** = *thread / quest-log* continuity ("last week Mara said X").

### 24A — Continuity spine + runtime ComfyUI removal ✅

- New `engine/journal.py` `NarrativeJournal`: rolling rendered prose
  (`recent_beats`) + scene/day/week summary layers. `recent_context()`
  grounds the LLM with immediate continuity, distinct from the arc digest.
- `llm.build_llm_prompt` grounds the two tracks as separate labelled
  sections ("Moments before" vs "Story so far"); `summarise_narration`
  compresses beats (LLM + deterministic fallback). `session.close_scene`
  compresses a scene's beats at the event boundary.
- **Runtime ComfyUI generation removed** — image generation is build-time
  only now. `visual.py` faces fall back to stock/placeholder; the session
  no longer holds a `comfyui_client`. `comfyui.py` stays for the bake
  scripts. (Also fixed a long-standing test hang where `new_game` warmed
  faces against a live server.)

### 24B — Multi-beat events ✅

- `EventBlueprint.setup` (pre-choice premise) + `BranchOutcome
  .action_summary` / `reaction_summary` (optional; `summary` is the
  result beat + single-beat fallback). `NarratedBeat` carrier.
- `session.narrate_setup` / `narrate_event` produce ordered
  `action → reaction → result` beats, each recorded into the journal
  before the next. `drama_block` / `postgame_block` iterate them.
- Arc-recap beat: `narrate_arc_recap` surfaces the thread track when an
  arc resumes after a day gap — needs `OutcomeRecord.day_ordinal` +
  `WorldClock.day_ordinal`.
- Authored full beats on 5 marquee events (conflict blame→apology arc,
  vuln.post_loss_confession, romantic.quiet_evening, mentor.quiet_word).

### 24C — Player presence / dynamic stance ✅

- `PlayerStance` (actor / reactor / onlooker / spectator). The
  blueprint's `player_stance` is an **anchor**, not the final value;
  `events.weighted_player_stance` samples the actual stance per instance
  (anchor bias × trait tilt × prior-stance persistence × chance, RNG-
  injected). Stamped on `OutcomeRecord.player_stance`; resolved once per
  event via `session.resolve_player_stance`.
- Drives figure framing (`figure_layout.PlayerFraming` FOREGROUND / ASIDE
  / BACKGROUND) + a scene-intro perspective note (`perspective_note`).

### 24D — Tone proximity + mid-event shift + cast escalation ✅

- `EventTone → FigureDistance` (`session._TONE_TO_DISTANCE`) for figure
  proximity; posture already followed tone (`figures.posture_for`).
- `BranchOutcome.result_tone` re-frames figures (proximity + posture) for
  the reaction/result beats (`figure_layout_for(tone_override=...)`,
  `session.result_tone_for`).
- `session.cast_chained_event` carries a prior cast forward (pins shared
  roles, casts new ones fresh) for 2→3→4 cast growth.

### 24E — Periodic journal summaries + tone audit ✅

- `NarrativeJournal.current_day` + `roll_day` / `roll_week`;
  `session.update_journal_period` (day rollover) + `summarise_week` (week
  end) compress the journal so long-horizon grounding stays bounded.
  `recent_context()` fallback descends beats → scene → day → week.
- Tone audit across all 55 blueprints — catalogue largely consistent.

### 24F — Multi-limit pagination ✅

- `narrative.paginate` caps each page by whichever limit binds first:
  `PAGE_MAX_SENTENCES` (2), `PAGE_MAX_WORDS`, or `PAGE_MAX_CHARS`.
- A single sentence too long for one page breaks mid-sentence with an
  em-dash continuation (`_split_long_sentence`): the page ends `" —"`,
  the next begins `"— "`, sized so the marked page still fits.
- Ordering (from `narrative_adjustments.md`) already holds: each beat's
  text is fully LLM-resolved before `drama_block` shows its pages;
  setup/recap are produced pre-choice, action/reaction/result post-choice.

**Deferred from Phase 24:**

- **General dynamic role assignment** — extend the weighted stance
  resolver to *all* participants (not just the player), with persistence
  + trait weighting on casting. Shares the anchor + weighted-resolver
  pattern with the tone rework below (build one `weighted_resolve` helper).
- **Escalating-cast content** — author a chained event that adds a role
  mid-scene, actually exercising `session.cast_chained_event` (the helper
  exists and is tested; no content uses it yet).
- **Event-taxonomy / tone rework (Phase 25, in progress)** — see the
  Phase 25 section below and `field_and_heart_event_tone_adr.md`.

## Phase 25 — Event taxonomy / tone rework (in progress)

Design + migration plan: `field_and_heart_event_tone_adr.md` (ADR-001).
Reframes tone from an identity axis into one dimension of a continuation
**state vector** `(domain, nature, tone, time, location)`; follow-ups are
generated by perturbing a subset of axes (≥1, <all) — three mechanisms:
authored / outcome-scheduled **arc** continuation, **contextual**
(dimensional perturbation), and future **player movement**. The Phase-17
`VALID_EVENT_COMBINATIONS` + `chains_from`/`_chain_bias` are interim
scaffolding the contextual engine supersedes.

### 25.1 — `EventType` value object ✅

- `EventId → EventType = (domain, nature, possible_tones)` with **natural
  identity** (tone set is part of identity — differing tone sets are
  different types; no privileged `essence()`). `tone`/`.tone` is a
  transition bridge (single-tone authoring still works; `.tone` exposes a
  representative for scalar readers). `to_dict`/`from_dict` round-trip the
  set + accept legacy single-tone saves. Registry + chains left as interim
  exact-match scaffolding, clearly labelled. (25.1a rename, 25.1b reshape,
  25.1c natural-identity correction.)

### 25.2+ — remaining (per ADR action items)

- Tone resolver (`resolve_event_tone`) + `OutcomeRecord.resolved_tone`;
  replace static `event_id.tone` reads. Shares a `weighted_resolve` helper
  with dynamic roles (deferred item 1).
- Contextual-continuation engine (perturbation + per-axis scoring over the
  state vector) — likely its own ADR.
- Outcome-scheduled arc consequences (pending-event scheduler).
- Content overhaul to real multi-tone sets (folds in the 24E retones);
  lands only after the continuation engine replaces exact-match chains.
- Player-driven movement (future ambition).

### Target behaviour — worked example (not yet implemented)

The contextual-continuation engine should generate a drifting sequence
where **each step perturbs exactly one axis** of `(nature, tone, domain)`
— the rest hold (continuity) while one moves (variation):

```
(Confrontation, Tense,    Sports)
  → (Confrontation, Romantic, Sports)        tone:   Tense → Romantic
  → (Invitation,    Romantic, Sports)        nature: Confrontation → Invitation
  → (Invitation,    Romantic, Relationship)  domain: Sports → Relationship
```

reading as: a tense on-pitch clash softens into charged tension, becomes
an invitation, then moves off the pitch into the relationship. Time and
location drift alongside (a domain shift may pull a location change, which
costs time).

Outcomes along the way **enqueue conditional future events** (the
outcome-scheduled arc mechanism) that *may* fire later under the right
circumstances — e.g. this thread might queue:

```
(Admission,   Romantic, Relationship)   a later confession
(Competition, Romantic, Sports)         rivalry recharged with romantic stakes
```

These sit in a pending-event pool with trigger conditions (cast present,
relationship state, time/location reachable) and are surfaced by the arc /
movement mechanisms when eligible — not fired immediately.

## Cross-cutting concerns (maintained throughout)

- **Testing**: every engine module has a unit test file. Notebooks are for exploration; `pytest` is the regression gate.
- **Determinism**: every random draw takes an injected `rng` (`numpy.random.Generator` or `random.Random`). No module-level `random` calls in the engine.
- **Serialization parity**: whenever a new field is added to a dataclass, update `save.py` in the same commit.
- **Derived observables are never set** — only computed. Tuple values change only as event side effects, never direct assignment.
- **Tier D is projection, not storage** — never materialize a Tier D seed into a full character record.
