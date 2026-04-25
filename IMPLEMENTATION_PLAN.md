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

## Phase 11 — Background animation (addendum §1)

Layered visual treatment on top of Phase 10.5's single-image scenes. Four independent layers (variant crossfade, noise overlays, time-of-day grade, mood grade) compose via Ren'Py ATL. Variation intent: subtle motion (light shifts, swaying foliage, candle flicker) — never camera-angle changes.

### 11A — Variant sets per node

- Extend `BackgroundEntry.image_path: str` → `image_paths: list[str]` (primary at index 0, variants at 1..N). Manifest schema bumps; old entries reload as single-variant.
- `BackgroundGenerator._generate_fresh` produces only the primary by default; `generate_variant(graph_id, node_name)` appends an additional path using primary as img2img anchor + a variation prompt suffix (very low denoise so variants are near-identical to primary). Placeholder producer emits subtle hue shifts to exercise the pipeline before SD lands.
- **Promotion policy:** `SceneGraphInstance.visit_counts: dict[node_name, int]` increments on `mark_visited`. Visit count 2 schedules variant 2 (background); visit count 3 schedules variant 3; cap at 3.
- **Eager warmup for marquees known at game start:** at `init_backgrounds`, scan all blueprint `LocationCue`s for marquee `graph_id`s, create those graphs eagerly, and schedule full 3-variant generation for the entry node. Other rooms still lazy-attach on first visit.
- New session methods: `scene_variants(graph_id, node) → list[Path]` (for Ren'Py crossfade); `scene_path` continues to return the primary.
- Save round-trip preserves `image_paths` and `visit_counts`.
- Tests: variant generation, visit-driven promotion, marquee warmup, manifest persistence.

### 11B — Colour grades

- New `engine/color_grades.py`: `TimeOfDay`, `Weather`, `SceneMood` enums + `ColorGrade` dataclass + the three lookup tables verbatim from addendum §1.3.
- `init_backgrounds` renders each grade as a solid-colour PNG into `game/assets/grades/` (deterministic, ~1KB each, cached on disk — regenerated only when the lookup table changes).
- **Atmosphere drivers:**
  - `time_of_day` advances per schedule slot (DAWN at slot 0, MORNING at 1, … wraps within a day).
  - `weather_tendency` drawn once per week at `start_week()`; per-day `weather` drawn from a biased distribution around the tendency (70% tendency, 30% drift to neighbours). Persisted on the schedule.
  - `mood` derived from `team_morale` + `momentum` via a small mapping table (e.g. high momentum + positive morale → EUPHORIC; bruising loss → MELANCHOLY; tight match → CHARGED).
- New `SceneAtmosphere` carrier; `session.atmosphere() → SceneAtmosphere`; `session.grade_paths() → tuple[Path, Path]` returns `(time_of_day_grade, mood_grade)`.
- Tests: PNG generation determinism, weather draw distribution under tendency, mood derivation table, atmosphere round-trip with save.

### 11C — Noise overlays

- New `engine/overlays.py`: `NoiseOverlay`, `OverlayAnim` enums + `OverlaySpec` + `OVERLAY_SPECS` and `SCENE_OVERLAYS` tables.
- Bridge: thin `LocationKind → list[NoiseOverlay]` map (no full `SceneType` refactor; that's Phase 16). House → grain + dust; school → grain; gym → grain; pitch/stadium → grain + crowd; pool → grain + shimmer.
- Procedural overlay generation at `init_backgrounds`: PIL noise functions write `grain.png`, `dust.png`, `shimmer.png`, `rain.png`, `crowd.png` into `game/assets/overlays/` if missing. Deterministic seed per overlay so regen reproduces. Cached across sessions.
- Weather-conditional overlays merged at lookup time: rain weather adds `RAIN_STREAK` regardless of scene type; clear midday outdoor scenes add `HEAT_SHIMMER`.
- New `session.overlays_for(graph_id, node) → list[OverlaySpec]` returning the merged stack.
- Tests: spec registry, scene-kind mapping, weather merge, deterministic PNG generation, regen-on-missing.

### 11D — Ren'Py ATL composite

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
- No automated tests — manual smoke checklist: visit `player_home` in two events (verify variant crossfade if 2+ variants), advance schedule slots (verify time-of-day grade swap), force a rainy week (verify rain overlay).

**Exit criteria:** background animation visibly conveys time-of-day, weather, and mood without regenerating images mid-scene; variant crossfade reads as breathing motion (not a hard cut to a different shot); marquee scenes pre-warm at game start, ad-hoc scenes promote on revisit.

**Deferred from this phase:**
- Real img2img variants (still placeholder until SD pipeline lands)
- `SceneType` / `SceneInstance` enum + global `SCENE_ADJACENCY` (Phase 16)
- Camera-angle variants and parallax depth (separate feature)

## Phase 11.5 — World clock + slot grid (refactor)

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

### 11.5A — Parallel clock (no schedule grid yet)

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

### 11.5B — Schedule grid + event durations

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

### 11.5C — Movement costs

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

## Cross-cutting concerns (maintained throughout)

- **Testing**: every engine module has a unit test file. Notebooks are for exploration; `pytest` is the regression gate.
- **Determinism**: every random draw takes an injected `rng` (`numpy.random.Generator` or `random.Random`). No module-level `random` calls in the engine.
- **Serialization parity**: whenever a new field is added to a dataclass, update `save.py` in the same commit.
- **Derived observables are never set** — only computed. Tuple values change only as event side effects, never direct assignment.
- **Tier D is projection, not storage** — never materialize a Tier D seed into a full character record.
