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

## Phase 5 — Schedule, arcs, clocks, save (technical §5.3, §7, §8)

- `schedule.py`: `WeekSchedule`, `EventSlot`, `BlockType`, skeleton generator, `force_next`.
- `arcs.py`: blueprint graph traversal, arc event detection (via `carries_arc_context`).
- Clock system: `Clock`, `ClockTick`, `tick_clocks`, integration into `compute_weight`.
- `save.py`: `serialise`/`deserialise` covering characters, outcomes, clocks, schedule, relationships.

**Exit criteria:** a multi-week headless simulation in a notebook runs drama → pregame → phases → postgame, with at least one clock reaching threshold and forcing an event. Save → load → resume produces identical continuation.

## Phase 6 — Ren'Py shell (technical §7.2)

- Minimal `game_loop.rpy`, `drama_block.rpy`, `game_block.rpy`, `postgame_block.rpy`.
- Placeholder `ui_screens.rpy` for schedule overview and relationship panel.
- Engine instantiated once; Ren'Py labels call engine methods and display returned strings. No custom logic in `.rpy` files beyond flow control.
- Hook Ren'Py's save system to `engine.save.serialise/deserialise`.

**Exit criteria:** Ren'Py project runs end-to-end on text only (no sprites, default background). Player can play through a week, save, quit, reload.

## Phase 7 — Visual prototype (technical §9)

- `visual.py`: `CharacterVisual`, `Expression`, `Pose`, `TeamPalette`, `SpriteLayer`, `render()` dispatching to `_render_flat`.
- `EXPRESSION_OVERLAYS` + `apply_overlay` with disk cache.
- Face generation (`FaceGenerationSpec`, `generate_face`) via ComfyUI or SD API; cache to `generated/faces/` with fixed seeds.
- Tier D face pool (~20–30 images) keyed by `age_group × build × gender_presentation`.
- Background generator (`BACKGROUND_PROMPTS`, `get_background`) with prompt-hash cache.
- Ren'Py `show_character` / `set_background` labels wired to `CharacterVisual.render()`.

**Exit criteria:** every scene displays a generated background and character portrait with mood-appropriate tinting. Generation never blocks mid-scene (session-start warm-up or lazy-on-first-access).

## Phase 8 — LLM narration (technical §6.3)

- `llm.py`: Ollama client, `build_llm_prompt`, `ollama_generate`, silent fallback to filled template.
- Per-event-type opt-in flag; default off for low-drama events, on for postgame/vulnerability/romantic.
- Prompt includes arc summary, previous outcome, cast, filled template, constraint to "keep names and facts."

**Exit criteria:** with LLM enabled, high-drama scenes read more varied than template-only; with LLM disabled or unavailable, game still plays identically using filled templates.

## Phase 9 — Content authoring

- Expand event library to cover all categories in design §8 (pregame, in-phase, momentum, goal, break, late-game, end, post-game; training, downtime, conflict, vulnerability, romantic, external-pressure, mentor/rival, celebration).
- Author 4–5 templates per event type (design §7.4 target).
- Build first full season of one playthrough's worth of arc chains (mentor arc, rivalry arc, romance arc, contract-pressure arc).
- Tune weights and clock thresholds from playtest data.

**Exit criteria:** a full-season playthrough surfaces distinct-feeling scenes with minimal repetition.

## Phase 10 — Composite sprites

- Populate `CharacterVisual.layers` per named character. `render()` automatically routes to `_render_composite`.
- Author body/kit/hair/expression/accessory layer sets.
- Palette-tinted rendering via per-layer shader.
- Procedural layer assembly for Tier D from a pool of parts.

**Exit criteria:** all Tier A + Tier B characters use composites; prototype face-image code path is unreachable and can be removed.

## Cross-cutting concerns (maintained throughout)

- **Testing**: every engine module has a unit test file. Notebooks are for exploration; `pytest` is the regression gate.
- **Determinism**: every random draw takes an injected `rng` (`numpy.random.Generator` or `random.Random`). No module-level `random` calls in the engine.
- **Serialization parity**: whenever a new field is added to a dataclass, update `save.py` in the same commit.
- **Derived observables are never set** — only computed. Tuple values change only as event side effects, never direct assignment.
- **Tier D is projection, not storage** — never materialize a Tier D seed into a full character record.
