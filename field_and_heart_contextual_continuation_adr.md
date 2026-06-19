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
2. **Perturbation target.** Derive a *target* vector that holds most axes
   and drifts a small subset (default: one), along per-axis adjacency,
   honouring correlations (`location ↔ domain`, `location ↔ time`). The
   perturbation is RNG-weighted, not fixed, so the drifting axis varies.
3. **Per-axis compatibility score.** Score each eligible candidate
   blueprint against the target: tone (resolved-target ∈
   `possible_tones`, or valence-adjacent), domain/nature (match vs
   adjacency), location (`valid_scene_types` compatible with the target
   location). The score becomes a multiplicative `contextual_bias` in
   `compute_weight`.
4. **Selection.** The existing weighted sampler picks among eligible
   candidates; high-compatibility (near the drifted target) candidates are
   favoured, so the realised sequence drifts one axis at a time.

`VALID_EVENT_COMBINATIONS` is retired as a gate (it remains, if anything,
an authoring coverage aid). The realised next event is grounded by the
**journal** (prose continuity) and stamps its own resolved vector for the
following step.

### Axis model

| Axis | Source | Drift / adjacency |
|------|--------|-------------------|
| domain | `EventType.domain` | adjacency table (e.g. SPORT↔RELATIONSHIP common; SECRET rare) |
| nature | `EventType.nature` | adjacency table (e.g. CONFRONTATION→ADMISSION; INVITATION→COLLABORATION) |
| tone | resolved tone (`resolve_event_tone`) | `TONE_VALENCE` adjacency (already defined) |
| time | `WorldClock` | advances as a *consequence* of other drifts (movement cost) |
| location | `current_location` / `valid_scene_types` | scene-graph adjacency (`engine.scene_taxonomy` already has `SCENE_ADJACENCY`); correlated with domain |

Tone adjacency reuses `TONE_VALENCE`; location adjacency reuses
`scene_taxonomy.SCENE_ADJACENCY`. Domain and nature adjacency tables are
**new authored data** (small, like the tone valence map).

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

The core new surface is small and authored (domain/nature adjacency
tables, a perturbation policy, a scoring function) — all pure + rng-
injected + unit-testable, mirroring `resolve_event_tone`.

## Consequences

**Easier / unlocked:**
- The worked-example single-axis drift becomes expressible.
- `_chain_bias` + `VALID_EVENT_COMBINATIONS` retire as the continuation
  mechanism (the last interim scaffolding from Phase 17).
- A single scoring surface that movement (later) can reuse.

**Harder / to revisit:**
- New authored adjacency tables (domain, nature) need taste + tuning, with
  distribution tests (drift is single-axis-dominant, not chaotic).
- Bounded by slot tag-routing until movement; the realised drift is within
  a slot's candidate pool.
- Location axis needs the prior event's location — likely a new
  `OutcomeRecord.location` (open Q1).

**Out of scope (separate, sequenced after):**
- **Outcome-scheduled pending events** (the "future consequence" arc half)
  — its own component; this ADR covers the *contextual* mechanism.
- **Player movement** — consumes this scoring surface; future.

## Open questions

1. **Store location on `OutcomeRecord`?** The location axis of the prior
   vector needs it; `current_location` drifts after. Lean: add
   `OutcomeRecord.location: tuple[str,str] | None`.
2. **Adjacency tables** — author domain/nature adjacency, or start with
   "hold or uniform-drift" and add structure once it reads wrong?
3. **Perturbation count** — strictly one axis per step, or weighted
   1-mostly-2? The worked example is exactly one.
4. **Coexistence with `BLOCK_TAGS`** — does the contextual target also
   nudge *which slot/tag* is favoured, or only rank within a slot's pool?
5. **Correlation mechanics** — how a domain drift pulls a location change
   and how that books time (ties into movement-cost accounting in
   `resolve_scene`).

## Action Items (proposed Phase 25.4)

1. [ ] **Axis adjacency data.** `TONE_VALENCE` (exists),
       `SCENE_ADJACENCY` (exists); add small authored `DOMAIN_ADJACENCY`
       and `NATURE_ADJACENCY`. *(Resolves Q2.)*
2. [ ] **Vector + perturbation.** A `ContinuationVector` (or read axes
       off the last record + world) and `perturb(vector, rng) → target`
       (single-axis-dominant, correlated). Pure + rng-injected.
3. [ ] **Scoring.** `contextual_score(candidate_event_type, valid_scene
       _types, target) → float` over the axes.
4. [ ] **Integrate.** Replace `_chain_bias` with `contextual_bias` in
       `compute_weight`, reading the last outcome's resolved vector.
       Retire / demote `VALID_EVENT_COMBINATIONS` + `CHAIN_EDGES`.
5. [ ] **Location axis.** `OutcomeRecord.location` (Q1); stamp on resolve.
6. [ ] **Tests.** Perturbation is single-axis-dominant + correlation-
       respecting; scoring favours near-target candidates; a multi-step
       headless run reproduces a drifting sequence; determinism.
7. [ ] **Docs.** Update `CLAUDE.md` + `IMPLEMENTATION_PLAN.md`; mark the
       Phase-17 chain/registry scaffolding superseded.

**Sequenced after:** outcome-scheduled pending events; then player
movement (reuses the scoring surface).
