# Field & Heart — Claude guide

Sports drama simulation. Python engine + Ren'Py presentation. See `field_and_heart_design.docx` (systems, feel, character model) and `field_and_heart_technical.docx` (data model, pipelines, code shape). `IMPLEMENTATION_PLAN.md` tracks phase progress.

## Architecture in one line

**Engine is pure Python; Ren'Py is a display shell that calls the engine.** Ren'Py labels must contain flow control only — no simulation logic, no stat math, no event selection.

## Directory layout

```
game/
  engine/      # pure Python simulation — all logic lives here
  content/     # authored data (events, templates, arcs) — never code
  scripts/     # Ren'Py .rpy labels — display + flow only
  assets/      # images, audio, fonts
notebooks/     # prototyping and distribution validation
```

When adding a new capability, ask: is this **logic** (→ `engine/`), **authored content** (→ `content/`), or **display** (→ `scripts/`)? Keep the boundary strict.

## Character model invariants

Three conceptual layers — violate these and the whole design collapses:

1. **Tuple layer** (`StatTuple`: value, awareness, focus, weight). Changes slowly, only as a side-effect of events. **Never assign tuple values directly from event handlers.** A confidence-boosting event shifts the named-stat value; the tuple drifts probabilistically over time.
2. **Named stats** — the event targets. Partially visible.
3. **Derived observables** (arrogance, composure, warmth, …) — **computed, never stored, never set.** Always via `character.observable(ObservableName.X)`.

"Insecurity as a trait" is not a field — it falls out of `focus × (1 - awareness)` across the tuple. Don't add it as stored state.

## Character tiers

- **Tier A**: player + story-relevant promotions. Full tuple per stat. Full event history.
- **Tier B**: named recurring (teammates, staff, league opponents, drama NPCs). Flat stat values, no tuple.
- **Tier D**: ad-hoc (cup opponents, one-scene NPCs). Stored as a `TierDSeed`; attributes are **projected** on demand via `project()`. **Never materialize a Tier D seed into a full character record.**

Tier promotion (B → A) infers a tuple from the existing flat value plus randomisation.

## Event system

- Events are `EventBlueprint`s loaded from `content/events/`. Blueprints define role slots, scene blocks, prereqs/unlocks/disables, weight rules, and **authored outcome summaries per branch**.
- Selection: filter by prereqs and castability, weight-sample the eligible set. Clocks add to weights and can force-insert at threshold.
- **Arc continuity is carried by `OutcomeRecord.arc_summary`** — a digest-append chain. No global story state. An event with `carries_arc_context=True` appends its summary to the prior one.
- **Outcome summaries are authored strings** — they go into templates and (optionally) into LLM prompts as grounding. Write them to read naturally in both roles.

## Narrative system

- Templates do structural work; the LLM is an **enhancer, not a generator**. Filled template is always the fallback.
- `TemporalRef` controls narrative distance: `NONE` / `IMMEDIATE` / `TRIGGER` / `ARC`. A reflective character gets arc-distance templates weighted up — **template pool does characterisation, don't hard-code character voice.**
- Slots resolve via `SLOT_RESOLVERS` (state-aware functions), not string substitution. When adding a slot, add a resolver.
- Target 4–5 templates per event type for sufficient variety without LLM.

## Simulation rules of thumb

- **Stamina contribution decays with fatigue each phase.** Other stats don't.
- **Perceived performance ≠ actual performance.** Self-evaluation is filtered through awareness noise and insecurity amplification. A low-awareness player's mood can move opposite to their actual contribution — this is a feature.
- **Momentum is shared team state**, not per-player.
- **Motivators shift output, not stats.** They decay; high focus slows decay; negative tuple weight can invert them.

## Coding conventions

- Dataclasses for all engine state. JSON-serializable via `save.py`. Any new field → update `save.py` in the same change.
- **Inject RNG.** No module-level `random.random()` or `np.random.*` in the engine — take a `Generator` / `Random` parameter. Determinism is required for testing and save resumption.
- **Enums for stat and observable names** (`StatName`, `ObservableName`, `CharacterRole`, `Disposition`, etc.). String keys only at the content-loading boundary.
- NumPy for vectorised phase math (`simulate_phase`). Plain Python everywhere else.
- Type hints on all public engine APIs.

## Ren'Py rules

- Import the engine once, store on the Ren'Py global `engine` object. All other `.rpy` files call methods on it.
- `.rpy` labels receive strings / paths from the engine and display them. No stat math, no selection logic, no narration assembly in `.rpy`.
- Ren'Py's save system calls `engine.save.serialise` / `deserialise`. Don't duplicate state in `.rpy` globals.
- **Image paths: the engine returns absolute filesystem paths, but Ren'Py's loader resolves image names *relative to `game/`* and searches its index — an absolute path is silently "couldn't find file" (it strips the leading `/` and searches the rest as a game-relative name).** Always convert engine paths to game-relative before `Image()` / `show expression` / `scene expression`. Use `_fh_image()` (scene_compose.rpy) which strips the `config.gamedir` prefix.

## Visual pipeline

- `CharacterVisual.render()` is the abstraction seam. Ren'Py only calls this. Prototype returns flat generated face + overlay; final returns composite layer render. **Swapping prototype → final must not touch any `.rpy` file.**
- **Image generation is build-time only (since Phase 24A).** Runtime serves pre-baked / stock assets and never calls ComfyUI — `CharacterVisual` falls back to the assigned stock face or a deterministic placeholder; backgrounds come from the pre-baked scene-graph pipeline. ComfyUI (`comfyui.py`, `ComfyUIImageProducer`) is retained **only** for the bake scripts (`scripts/prebake_assets.py`, `figure_bake.py`, `generate_sprites.py`, `generate_stock_faces.py`). Do not reintroduce a runtime `comfyui_client` on the session.
- Fixed seeds per character ID so the same character always produces the same face. Cache to disk.

## Testing and validation

- `pytest` is the regression gate. Every engine module has a matching `tests/test_*.py`.
- Notebooks in `notebooks/` are for exploration and distribution validation — not a substitute for unit tests.
- Validate simulation distributions (mean ≈ composite over many runs, variance bounded, fatigue trajectory monotonic) whenever phase-sim math changes.

## What to avoid

- Coupling simulation to Ren'Py (importing `renpy` from `engine/` — ever).
- Direct assignment to tuple values or derived observables.
- Materializing Tier D seeds.
- Global random state in engine code.
- LLM as source of truth for plot facts (it rephrases; template carries the facts).
- New per-character fields that duplicate something derivable from the tuple distribution.

## Current phase

See `IMPLEMENTATION_PLAN.md`. Latest shipped: **Phase 24 — narrative flow** (see below). Phases 22–23 (presentation + pre-baked rendering) precede it.

Phase 22 — presentation pass closing the engine→screen gap. Done: 22A save integrity (`runtime.rpy` `fh` holder keeps the unpicklable session out of Ren'Py's store; engine state rides native saves as `fh_save_blob`, rebuilt in `after_load`; rollback disabled), 22B event routing, 22C generalised choice menu, 22D scene intros + sprite wiring + authored `ChoiceNode` labels + scene-intro LLM pass, 22E category template pools (zero generic-only blueprints), 22F match narration + in-phase playable beats (teammate goal → `select_match_event`/`cast_match_event`/`resolve_match_event`, `cast_event(pinned=...)`), 22G lint gate, 22H LLM default model (`liquid/lfm2-24b-a2b`) + reasoning-block stripping, 22I launcher (`play.command`), 22J gender-aware narration (pronoun resolvers `{they:player}` etc.; templates + 142 branch summaries de-gendered; LLM pronoun grounding). Remaining: more authored ingame beats (player-scored, near-miss). Gates: `scripts/check.sh` (pytest + renpy lint) before committing under `game/scripts/`; `scripts/check_summary_pronouns.py` after editing branch summaries. Narration is third-person past tense; use role-scoped pronoun slots, never hardcoded he/she.

Phase 23 — pre-baked rendering (largely shipped): build-time background pre-bake replaces runtime on-demand SD. Alternates model (`SceneGraphSpec.alternates`, `SceneGraphInstance.node_alternates`, `attach/get/choose_alternate` — distinct shots per visit, separate from motion variants); `PrebakedImageProducer` + `init_backgrounds(prebaked=True)` + `NoOpPrefetchScheduler`; `scripts/prebake_assets.py` idempotent manifest-driven driver; hot-tier + gap specs baked (74 shots: residences, team_hq, venues, bar/media/transit); runtime wired (prebaked `resolve_scene` redirects every cue to the canonical `spec_id` graph; `release_scene` no-op). New `LocationKind`s: TEAM_HQ, TRAINING_GROUND, BAR, MEDIA, TRANSIT. Locked painterly recipe in `ComfyUIImageProducer` (euler/sgm_uniform, negative prompt, 32 steps). Design: `field_and_heart_prebake_rendering.md`. Next: face-less painterly **figure** assets (`field_and_heart_figure_assets.md`) — look/matting/composite de-risked; engine work starts with persisting `CharacterDescriptor` on characters for consistent figure selection.

Phase 24 — narrative flow (shipped): the pass that makes LLM fragments read as a flowing scene. Design notes in `narrative_adjustments.md`. **Two continuity tracks, kept strictly separate — never conflate.** (1) **Journal** (`engine/journal.py`, `NarrativeJournal`) = *temporal* continuity: rolling rendered prose + scene/day/week summaries, compressed beats→scene (`close_scene`)→day (clock day-rollover via `update_journal_period`)→week (`summarise_week` at week end); `recent_context()` fallback descends beats→scene→day→week. (2) **Arc** (`engine/arcs.py` + `OutcomeRecord.arc_summary`) = *thread / quest-log* continuity; surfaced by `narrate_arc_recap` when a storyline resumes after a day gap (`OutcomeRecord.day_ordinal` + `WorldClock.day_ordinal`). Both ground the LLM as distinct labelled sections ("Moments before" vs "Story so far") in `llm.build_llm_prompt`. **Events play as multi-beat scenes** (24B): `setup → choice → action → reaction → result`, each its own screen, each fed into the journal before the next — `EventBlueprint.setup`, `BranchOutcome.action_summary`/`reaction_summary` (optional; `summary` is the result beat + single-beat fallback), driven by `session.narrate_setup`/`narrate_event` (`NarratedBeat`). **Player presence is a dynamic stance** (24C): `PlayerStance` (actor/reactor/onlooker/spectator) — the blueprint's `player_stance` is an *anchor*, the actual stance is sampled by `events.weighted_player_stance` (anchor bias × trait tilt × prior-stance persistence × chance), stamped on `OutcomeRecord.player_stance`, resolved once per event via `session.resolve_player_stance`; drives figure framing (`figure_layout.PlayerFraming`) + a scene-intro perspective note. **Tone drives figures + can shift mid-event** (24D): `EventTone → FigureDistance` (`session._TONE_TO_DISTANCE`) for proximity, `posture_for` for posture; `BranchOutcome.result_tone` re-frames figures for the reaction/result beats (`figure_layout_for(tone_override=...)`); `session.cast_chained_event` carries a prior cast forward (pins shared roles, casts new ones) for 2→3→4 cast growth. **Pagination** (24F): `narrative.paginate` caps a page by whichever binds first — ≤2 sentences / `PAGE_MAX_WORDS` / `PAGE_MAX_CHARS` — and breaks a single over-long sentence mid-way with an em-dash continuation (`" —"` … `"— "`). **Deferred:** extend the weighted stance resolver to *all* participants (not just the player); author an escalating-cast chained event that actually exercises `cast_chained_event`; retone `external.media_scrum`→TENSE and `training.showing_off`→PLAYFUL (blocked — tone is part of the `EventId` triple + `VALID_EVENT_COMBINATIONS`, so it's a taxonomy change; flagged in-place).
