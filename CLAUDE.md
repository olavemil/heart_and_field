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

## Visual pipeline

- `CharacterVisual.render()` is the abstraction seam. Ren'Py only calls this. Prototype returns flat generated face + overlay; final returns composite layer render. **Swapping prototype → final must not touch any `.rpy` file.**
- Generation happens at session start or lazily on first scene access — **never block mid-scene.**
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

See `IMPLEMENTATION_PLAN.md`. The project has completed Phase 21 — real visuals: ComfyUIImageProducer replaces placeholder PNGs with SD3.5/Flux 2 generation via ComfyUI, SceneInstance→LocationDescriptor bridge for styled variant rendering, and session auto-selection of real vs placeholder producer. Phase 22 is next.
