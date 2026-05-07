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

### 11.5B — Schedule grid + event durations ✅

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
  - `compose_mechanical_description(secret, cast)` — deterministic, no LLM. Five templates (one per AspectType). Renders every aspect to a sentence and joins with `. `. Holder name resolved via `primary_holder()` (OWNER → PARTICIPANT → WITNESS → SUSPECT priority). Unmapped character ids fall through as the id itself so missing placeholder bindings show up in dev.
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

### 18C — Secret web generator

- New `engine/world_genesis.py`:
  - `generate_secret_web(rng, *, characters, secret_count_range)` —
    creates N secrets across the roster with cross-references that
    spawn `CharacterPlaceholder`s for unbound targets.
  - Runs `engine.secret_llm.initialise_secret` on each generated
    secret (with the world's `LLMClient` if available; falls back to
    deterministic phrases otherwise — the existing graceful path).
  - Surfaces `unresolved_references(state)` after generation so the
    integration tests can assert every placeholder is bookkept.
- Tests: secrets reference real characters where possible, fall back
  to placeholders otherwise; `unresolved_references` is empty after
  the bookkeeping pass; `initialise_secret` runs once per secret.

### 18D — `GameSession.new_game()` integration

- Extends `new_game(player_name, *, seed, customisation=None, …)` so
  the existing hardcoded Ren'Py roster path becomes a thin
  customisation override. With no customisation, the full 18A/B/C
  pipeline runs with the master seed.
- New `PlayerCustomisation` dataclass: name, role, optional quirk
  list, optional descriptor, optional starting stats. Empty fields
  fall through to randomisation.
- Ren'Py opening flow: name entry, role pick, "randomise me" /
  "customise" branch. Wires through `session.new_game(...)`.
- Tests: customisation overrides applied, master seed produces an
  identical world on re-run, save round-trip preserves the generated
  cast and secrets.

**Exit criteria for Phase 18:** typing `start` in Ren'Py produces a
randomly-generated world with named teammates, coach, opponent club,
secret memberships across the squad, and a first-week schedule —
without any hardcoded character data in the .rpy files. Re-running
with the same seed produces an identical world; running with a
different seed produces a meaningfully different one.

## Phase 19 — Content pass + chain bias

- Migrate existing `game/content/events/*.py` blueprints to use
  `EventId` triples.
- Wire `chain_edges` into `compute_weight` (chain bias multiplier
  keyed off the most recent `OutcomeRecord.event_id`).
- Wire `valid_scene_types` / `preferred_instances` into
  `LocationCue` resolution.
- Author blueprints for each `VALID_EVENT_COMBINATIONS` triple
  missing today.

## Phase 20 — League and progression (operational)

- League / club metadata (named opponents with fixed seeds).
- Season structure, standings, end-of-season events.
- Settings UI (LLM endpoint, model, on/off; visual generation
  toggle).

## Phase 21 — Real visuals

- Real `ImageProducer` for SD3.5 + img2img on graph anchors
  (replaces the placeholder PNG producer).
- `SceneInstance` propagation into `LocationDescriptor` so the
  generator can render a `BAR_LOCAL` differently from a `BAR_UPSCALE`.

## Cross-cutting concerns (maintained throughout)

- **Testing**: every engine module has a unit test file. Notebooks are for exploration; `pytest` is the regression gate.
- **Determinism**: every random draw takes an injected `rng` (`numpy.random.Generator` or `random.Random`). No module-level `random` calls in the engine.
- **Serialization parity**: whenever a new field is added to a dataclass, update `save.py` in the same commit.
- **Derived observables are never set** — only computed. Tuple values change only as event side effects, never direct assignment.
- **Tier D is projection, not storage** — never materialize a Tier D seed into a full character record.
