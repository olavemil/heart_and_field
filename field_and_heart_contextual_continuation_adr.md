# ADR-002: Contextual continuation — state-vector perturbation

**Status:** Proposed
**Date:** 2026-06-19
**Deciders:** Olav (project owner)
**Related:** ADR-001 (event taxonomy / tone); Phase 25; `narrative_adjustments.md`

## Context

ADR-001 reframed an event's descriptor as axes of a **state vector**
`(domain, nature, tone, time, location)` and named three continuation
mechanisms: authored/outcome-scheduled **arc**, **contextual**, and
future **player movement**. Phase 25.1–25.3 landed the tone axis
(`EventType`, `resolve_event_tone`, multi-tone content). This ADR
designs the **contextual** mechanism — the engine that picks the *next*
event by drifting from the last one — and the worked example it must
produce:

```
(Confrontation, Tense,    Sports)
  → (Confrontation, Romantic, Sports)        tone drifts
  → (Invitation,    Romantic, Sports)        nature drifts
  → (Invitation,    Romantic, Relationship)  domain drifts
```

Each step perturbs **one axis** (≥1, <all): continuity from what holds,
variation from what moves. Domain/nature/tone/location all drift;
time advances as a consequence (a domain or location change can pull a
location change, which costs time).

**What exists to build on / replace:**

- Selection is weighted sampling: `select_event(candidates, ctx, state,
  rng)` filters by prereqs/castability/secret-gating, then
  `compute_weight` multiplies `base × weight_modifiers × recency_penalty
  × quirk_bias × aspect_boost × _chain_bias`.
- `_chain_bias` is the **interim** continuation nudge (Phase 17): boosts
  blueprints whose `EventType` matches an authored `CHAIN_EDGES` edge from
  the last outcome's `taxonomy_id`. ADR-001 marked it (and
  `VALID_EVENT_COMBINATIONS`) scaffolding to be superseded *here*.
- Axes are available: `EventType.(domain, nature, possible_tones)`;
  resolved tone via `resolve_event_tone` + `OutcomeRecord.resolved_tone`;
  `WorldClock` (time) + `day_ordinal`; `GameState.current_location` and
  the blueprint's `valid_scene_types` (location affinity).
- Slots: `select_event_for_slot` routes by `BLOCK_TAGS` (a slot is
  DRAMA/TRAINING/…); the contextual engine must coexist with this until
  movement makes scheduling more free-form.

**Constraints:** deterministic (injected `rng`); never-block; selects from
**authored blueprints** (no procedural content generation — "generation"
means *choosing* a blueprint whose vector is near a perturbed target);
reuse the weighted-selection pipeline rather than replacing it.

## Decision

Model contextual continuation as **perturb-then-score**, delivered as a
weight contributor that **replaces `_chain_bias`**:

1. **Prior vector.** From the last `OutcomeRecord`, read
   `(domain, nature)` (taxonomy_id), `resolved_tone`, and time/location
   (from `WorldClock` + `current_location`; see open Q1 on storing
   location on the record).
2. **Perturbation (continuity-biased cascade — no adjacency tables).** The
   target holds most axes and drifts a few. Continuity comes from the axes
   that *hold*, not from constraining how a drifting axis moves — so a
   drifting axis just takes a different value (selection then finds the
   nearest available blueprint). Algorithm (`engine.continuation`):
   - If the prior outcome is **immediate** (not a scheduled event) and
     pushed an axis (e.g. a `result_tone` shift), apply that drift first
     and count it.
   - Consider the remaining axes in random order; each drifts with
     ``p = 3 / (4 + 2 * changes)``; **stop at the first axis that holds.**
   - Yields ≈ `0:25% 1:37% 2:23% 3:10% 4:4%` — mostly one or two axes
     move, ~25% none, a light tail for the occasional dramatic shift.
   - **Arc / scheduled events override** this entirely: a chained or
     outcome-scheduled event is respected (its own vector), bypassing the
     drift.
3. **Per-axis compatibility score (soft, no adjacency).** Score each
   eligible candidate by how many of the target axes it matches —
   domain/nature equality, location via `valid_scene_types`, tone via the
   existing resolver (`resolved-target ∈ possible_tones`, else valence
   closeness). *Soft* so that when the exact target has no/few blueprints
   the nearest available still wins (graceful, avoids starvation). Becomes
   a multiplicative `contextual_bias` in `compute_weight`.
4. **Selection.** The existing weighted sampler picks among eligible
   candidates; near-target candidates are favoured, so the realised
   sequence drifts a small number of axes per step.

`VALID_EVENT_COMBINATIONS` is retired as a gate (at most an authoring
coverage aid). The realised next event is grounded by the **journal**
(prose continuity) and stamps its own resolved vector for the next step.

### Axis model

| Axis | Source | On drift |
|------|--------|----------|
| domain | `EventType.domain` | take a different domain (selection finds nearest available) |
| nature | `EventType.nature` | take a different nature |
| tone | resolved tone (`resolve_event_tone`) | let the resolver pick freely (don't carry the prior tone); `TONE_VALENCE` still shapes it |
| time | `WorldClock` | advances as a *consequence* of domain/location drift (movement cost) |
| location | `current_location` / `valid_scene_types` | a new location — **conservative**: kept often by the cascade, and content must spread events across locations to avoid jarring jumps (see Q2) |

No domain/nature adjacency tables (per the algorithm): the cascade keeps
most axes, which is what produces continuity. Tone keeps reusing
`resolve_event_tone` + `TONE_VALENCE`. **Location is the sensitive axis** —
a jump with no narrative bridge reads badly, so location should drift
rarely (it does, being one of four cascade axes) and the content library
needs events spanning locations (open Q2); scene-graph adjacency
(`scene_taxonomy.SCENE_ADJACENCY`) remains available as a knob if free
location drift reads wrong.

## Options Considered

### Option A: Weight contributor replacing `_chain_bias` *(recommended)*

Perturb-then-score produces a multiplier folded into `compute_weight`;
selection stays as-is.

| Dimension | Assessment |
|-----------|------------|
| Complexity | Med (scoring + adjacency tables; reuses sampler) |
| Risk | Low (one weight factor swapped; slot routing untouched) |
| Fits current engine | Yes |
| Reaches the vision | Mostly — drift emerges from scoring; full free-form awaits movement |

**Pros:** incremental, testable in isolation, keeps determinism + slot
routing; directly retires the scaffolding it replaces.
**Cons:** still bounded by the slot's tag-filtered candidate pool until
movement loosens scheduling; "generation" is selection, not synthesis.

### Option B: Standalone contextual scheduler (bypass slots)

A new generator that, per free slot, computes the target vector and picks
a blueprint directly, ignoring `BLOCK_TAGS`.

| Dimension | Assessment |
|-----------|------------|
| Complexity | High (parallel selection path; reconcile with schedule) |
| Risk | Med–High (two selection paths; save/flow churn) |
| Fits current engine | Partially |
| Reaches the vision | Closer, sooner |

**Pros:** truer to the free-form target.
**Cons:** premature — duplicates selection, fights the slot/schedule model
before movement (which is what *motivates* free-form) exists.

### Option C: Procedural event synthesis

Generate event *content* for a target vector via templates/LLM rather than
selecting an authored blueprint.

**Rejected (for now):** conflicts with the "templates/engine are the
source of truth" invariant; enormous scope; the authored-blueprint library
is the design's backbone.

## Trade-off Analysis

A reuses the proven weighted-selection pipeline and swaps exactly one
factor (`_chain_bias → contextual_bias`), so it is low-risk and keeps
slot routing, determinism, and saves intact. The drift behaviour emerges
from scoring candidates against a perturbed target — enough to produce the
worked-example sequences within a relaxed candidate pool. B's free-form
scheduling is the eventual shape but is motivated by **player movement**
(which advances time and crosses locations outside the slot grid); building
it before movement means maintaining two selection paths. So: **A now**,
evolving toward B when movement lands. C is out of scope.

The core new surface is small (a perturbation cascade + a soft scoring
function) — pure + rng-injected + unit-testable, mirroring
`resolve_event_tone`. No adjacency tables: continuity is carried by the
*held* axes, so a drifting axis just takes a different value.

## Consequences

**Easier / unlocked:**
- The worked-example single-axis drift becomes expressible.
- `_chain_bias` + `VALID_EVENT_COMBINATIONS` retire as the continuation
  mechanism (the last interim scaffolding from Phase 17).
- A single scoring surface that movement (later) can reuse.

**Harder / to revisit:**
- Bounded by slot tag-routing until movement; the realised drift is within
  a slot's candidate pool.
- Location axis needs the prior event's location — likely a new
  `OutcomeRecord.location` (open Q1).
- **Content coverage**: the soft scorer needs blueprints spanning domains/
  natures/locations, or drift targets find no near match. Location
  especially — too few cross-location events ⇒ jarring jumps or no drift
  (Q2).

**Out of scope (separate, sequenced after):**
- **Outcome-scheduled pending events** (the "future consequence" arc half)
  — its own component; this ADR covers the *contextual* mechanism.
- **Player movement** — consumes this scoring surface; future.

## Open questions

1. **Store location on `OutcomeRecord`?** The location axis of the prior
   vector needs it; `current_location` drifts after. Lean: add
   `OutcomeRecord.location: tuple[str,str] | None`.
2. **Location content coverage** — ensure enough events span locations (or
   carry open/flexible locations) so location holds or drifts *with a
   bridge*, never teleports. Possibly constrain location drift to
   `SCENE_ADJACENCY` if free drift reads wrong.
3. ~~**Adjacency tables / perturbation count**~~ **Resolved:** no adjacency
   tables; continuity-biased cascade (stop at first hold), ≈25% no-drift,
   0-2-change mode. *(Landed: `engine.continuation.drift_axes`, 25.4a.)*
4. **Coexistence with `BLOCK_TAGS`** — does the contextual target also
   nudge *which slot/tag* is favoured, or only rank within a slot's pool?
5. **Correlation mechanics** — how a domain drift pulls a location change
   and how that books time (ties into movement-cost accounting in
   `resolve_scene`).

## Action Items (Phase 25.4)

1. [x] **Perturbation cascade.** `engine.continuation.drift_axes` — the
       continuity-biased cascade (stop at first hold; outcome-forced drifts
       pre-counted). No adjacency tables. Distribution-tested. *(25.4a.)*
2. [ ] **Prior vector + drift values.** Read the prior axes off the last
       record + world; for each drifted axis pick a new value (domain/
       nature: a different enum; tone: free-resolve; location: a different
       location). Add `OutcomeRecord.location` (Q1); stamp on resolve.
3. [ ] **Soft scoring.** `contextual_score(candidate_event_type,
       valid_scene_types, target) → float` — count matched target axes
       (graceful when the exact target is unauthored).
4. [ ] **Integrate.** Replace `_chain_bias` with `contextual_bias` in
       `compute_weight`, reading the last outcome's resolved vector.
       Retire / demote `VALID_EVENT_COMBINATIONS` + `CHAIN_EDGES`.
5. [ ] **Tests.** Scoring favours near-target candidates; a multi-step
       headless run reproduces a drifting sequence; determinism.
6. [ ] **Docs.** Update `CLAUDE.md` + `IMPLEMENTATION_PLAN.md`; mark the
       Phase-17 chain/registry scaffolding superseded.

**Sequenced after:** outcome-scheduled pending events; then player
movement (reuses the scoring surface).
