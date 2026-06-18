# ADR-001: Event taxonomy — `EventType`, tone as a carried soft-filter

**Status:** Proposed
**Date:** 2026-06-18
**Deciders:** Olav (project owner)
**Related:** Phase 24 (narrative flow); deferred item 1 (dynamic participant
roles); `narrative_adjustments.md`

## Context

`EventId(domain, nature, tone)` currently does double duty:

1. **Essence / connection** — chains connect events by `EventId`
   (`CHAIN_EDGES`, `chains_from`, `_chain_bias` reading the last outcome's
   `taxonomy_id`); `VALID_EVENT_COMBINATIONS` registers the legitimate
   triples; Phase 19 tests assert coverage + validity.
2. **Affect** — `tone` drives figure posture (`figures.posture_for`),
   proximity (`session._TONE_TO_DISTANCE`, Phase 24D), scene-intro
   atmosphere pools, and the LLM mood. Phase 24D's `result_tone` already
   lets the *displayed* tone diverge from the base tone mid-scene.

Two facts establish that `EventId` is a **categorical essence, not a
primary key** (the real PK is `blueprint.id`):

- The Phase 19 tests enforce only coverage and validity, never uniqueness
  (`covered_keys` is a set; duplicates collapse harmlessly).
- `_chain_bias` boosts **every** blueprint whose `event_id` matches a
  chain edge's `to_id`; multiple blueprints sharing an essence simply
  means weighted random selection among them — a *feature*, not a bug.
  Nothing builds a `{event_id: blueprint}` map.

**The forcing requirement (tone continuity):** when event A resolves to
tone T, the following event — random or arc-driven, constrained on domain
/ nature — should *respect* T (a warm thread stays warm unless something
shifts it). This means tone must flow between events as a carried signal.

**The tension this exposes:** if tone stays inside the connection key,
then either (a) tone is fixed per blueprint, forcing one-blueprint-per-tone
authoring (combinatorial blow-up: ~6–8 tones × every domain×nature cell),
or (b) tone is resolved per instance — but then the stamped `taxonomy_id`
carries a *rolled* tone, and chain edges keyed on a specific tone match
only probabilistically. **Variable/continuity-carrying tone is
incompatible with tone-in-the-connection-key.**

Non-functional constraints: a blueprint overhaul is already anticipated
(for variability + complexity), so a migration touching all ~55 blueprints
is acceptable *if* done deliberately. Determinism (injected RNG) and the
never-block / always-fallback narration discipline must hold. The solution
should reuse the Phase 24C/24D **anchor + weighted-resolver** pattern so it
shares conventions with deferred item 1 (dynamic participant roles).

## Decision

Treat `EventType` as the **inherent state of an event**, transformed
across a firing — not as a frozen identity.

- **Rename `EventId` → `EventType`** (avoid confusion with `blueprint.id`).
- **`EventType` = `(domain, nature, possible_tones: frozenset[EventTone])`**
  — the inherent state a blueprint declares: what the event structurally
  is, plus the tones it can plausibly carry. The tone-set lives **on
  `EventType`**; that is not a problem because nothing matches on the set
  directly — **only the resolved tone matters at the boundary.**
- **Continuation is driven by the outcome, not by structure.** What a
  follow-up must respect is the prior event's **resolved tone** (and, more
  broadly, its outcome state), *not* its domain/nature. Domain and nature
  *may* carry over but are soft preferences at most, never gates.
  Eligibility = a candidate `EventType.possible_tones` is **compatible
  with the carried resolved tone** (set membership / soft match). Because
  matching is on the resolved tone, a tone-*set* on `EventType` is sound —
  this dissolves the chain-incoherence problem (nothing keys on a frozen
  tone).
- **Carry the resolved tone (outcome state) between events.** The tone a
  firing resolves to is stamped on its `OutcomeRecord` (alongside
  `player_stance` / `day_ordinal`); it becomes the next event's inherited
  context. Selection biases toward candidates whose `possible_tones`
  overlap it, with context-driven drift.

This is a hybrid of the two framings the discussion produced (Option A's
economy + LLM conveyance, Option B's reliability) — see below.

### Event-state lifecycle (per firing)

```
EventType (inherent: domain, nature, possible_tones)
   │  ← inherited context from prior outcome (resolved tone, flags,
   │     morale, relationship state …) biases the resolution
   ▼
resolve tone  →  actual tone for THIS firing      (before narration)
   │  ← player action / choice outcome may shift it (24D result_tone is
   │     the existing special case)
   ▼
resolved outcome state (resolved tone + branch + flags + deltas)
   │  → stamped on OutcomeRecord; becomes the next event's
   ▼     inherited context (drives continuation eligibility/bias)
```

The carried signal is the **outcome state**, primarily the resolved tone
but extensible (flags, relationship deltas already on `OutcomeRecord`).
Tone is the first facet to wire; the shape allows richer continuation
signals later.

### Two continuity tracks (unchanged separation)

This reshapes the **emergent** continuity — the soft "what comes next"
bias (today `_chain_bias` + `OutcomeRecord.taxonomy_id`), which becomes
outcome/resolved-tone driven rather than `EventType`-equality driven. The
**explicit arc graph** (`prereq`/`unlock` walked by `blueprint.id` in
`arcs.py`) remains the *authored-thread* track — but it, too, should
respect the carried tone when it resumes (it already re-resolves prior
text in `narrate_arc_recap`).

## Options Considered

### Option A: LLM-conveyed tone + runtime-filtered outcome pool

Tone lives entirely at runtime; blueprints are tone-agnostic; the LLM is
told the target tone via prompt injection; branches are a larger pool
filtered by tone at selection time.

| Dimension | Assessment |
|-----------|------------|
| Complexity | High (branch-pool model change) |
| Authoring cost | Low |
| Reliability of tone | Low–Med (depends on LLM; offline fallback weak) |
| Chain coherence | OK (tone never in key) |
| Reuses 24C/24D pattern | Partially |

**Pros:** minimal authoring; maximal variation.
**Cons:** tone reliability hostage to the LLM (violates "template/engine is
the source of truth"); the variable-size, tone-filtered branch pool is a
big change to the branch/outcome model; weak deterministic fallback.

### Option B: Tone baked per blueprint (status quo, extended)

Keep tone in the identity triple; get variation by authoring one blueprint
per `(domain, nature, tone)` cell.

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low (no engine change) |
| Authoring cost | Very High (combinatorial) |
| Reliability of tone | High (authored) |
| Chain coherence | OK only while tone is *fixed* — blocks carried/variable tone |
| Reuses 24C/24D pattern | No |

**Pros:** reliable, fully authored tone; no engine change.
**Cons:** combinatorial authoring; **cannot** support carried/variable
tone (the forcing requirement) without breaking chain matching; retoning
an event is a taxonomy change (the Phase 24E friction).

### Option C: `EventType` as inherent state (`domain, nature, possible_tones`) + carried resolved tone *(recommended)*

`EventType` carries the structural facets *and* the tone-set it can serve;
the resolved tone is carried between events as a soft-filtered,
drift-capable signal; continuation matches a candidate's `possible_tones`
against the carried resolved tone (set membership), with domain/nature as
soft preferences at most.

| Dimension | Assessment |
|-----------|------------|
| Complexity | Med (wide but mechanical migration) |
| Authoring cost | Med (one blueprint serves several tones) |
| Reliability of tone | High (engine knows supported tones; branches authored to fit; LLM colors the specific tone) |
| Continuation coherence | High (matches on *resolved* tone, never a frozen one) |
| Reuses 24C/24D pattern | Yes (anchor + weighted resolver, stamped for continuity) |

**Pros:** reconciles continuity + variation + coherence; reliability of B
with much of A's economy; retoning becomes a plain field edit; `VALID_*`
becomes the cleaner domain×nature "structural kinds"; shares the resolver
with item 1.
**Cons:** wide migration (EventType, registry, chain edges, ~55
blueprints, tests); branches must be written to read across a blueprint's
declared tone-set (mitigated: pronoun/tone-neutral summaries + LLM coloring
+ 24D posture/proximity).

## Trade-off Analysis

The forcing requirement (carried tone continuity) **eliminates Option B** —
fixed-in-key tone cannot carry. The choice is A vs C, and it turns on where
tone reliability comes from. Option A leans on the LLM, which conflicts
with the project invariant that the filled template / engine is the source
of truth and the LLM only enhances; its offline behaviour would be weak.
Option C keeps tone *engine-known* (a blueprint declares its set, branches
are authored to fit, the resolved tone is deterministic) while still
delegating the *prose coloring* of the specific tone to the LLM — the same
division of labour as everywhere else in the engine.

C's cost is a migration, but it is mechanical and the blueprint overhaul is
already planned. C also pays compounding dividends: it is the same
anchor + weighted-resolver shape as Phase 24C (player stance) and deferred
item 1 (participant roles), so building it establishes the shared
convention for those.

**Soft vs hard tone match (sub-decision):** prefer a **soft** bias with
drift over a hard filter. A hard "only tone-T blueprints are eligible"
risks emptying the candidate pool and reads rigidly. Carry T as a *target*;
weight tone-overlapping blueprints up; allow context (morale, momentum,
relationship, arc) to drift the resolved tone to adjacent tones. Anchor
dominates, context shapes, chance breaks ties — the 24C/24D discipline.

## Consequences

**Easier:**
- Retoning an event = a one-line `tones` edit (no registry churn) — closes
  the Phase 24E deferred item.
- Carried tone continuity (A→T→B) becomes expressible.
- Per-instance tone variation for free across all downstream rendering.
- One blueprint covers several tones → fewer blueprints for full coverage.
- Continuation is outcome-driven: a follow-up is chosen for *how the last
  beat landed* (resolved tone), not just what kind of beat it was —
  domain/nature carry only as soft preference.

**Harder / to revisit:**
- A wide one-time migration (see Action Items).
- Branch summaries must read across a blueprint's tone-set; authors gain a
  new responsibility (declare a sensible `tones` set; keep summaries
  tone-flexible or rely on LLM coloring).
- `VALID_EVENT_COMBINATIONS` changes meaning (domain×nature); the coverage
  test relaxes from "exactly one per triple" to "≥1 blueprint per essence."
- The tone resolver's weighting model (which context signals, how much
  drift) needs tuning and distribution tests, like the 24C stance resolver.

**Explicitly out of scope (deferred):** Option A's variable-size,
tone-filtered *outcome pool* — a separate branch-model change. The hybrid
gets most of the value with authored branches + LLM coloring first.

## Open questions (resolve during design)

1. ~~**`tones` on `EventType` vs the blueprint.**~~ **Resolved: on
   `EventType`** — `EventType = (domain, nature, possible_tones)` is the
   inherent event state, and the tone-set is useful precisely for matching
   follow-ups. Safe because matching is on the *resolved* tone, never the
   set.
2. **Default `possible_tones`** for unannotated `EventType`s — all tones,
   or a conservative `{NEUTRAL}`? Affects migration ergonomics.
3. **Resolver weighting** — exact context signals and drift width; whether
   to share a generic `weighted_resolve(anchor, candidates, context, rng)`
   helper with the item-1 role resolver.
4. **Arc-recap interaction** — should the recap beat reflect the tone the
   prior thread resolved to? (Likely yes — it already re-resolves prior
   text in `narrate_arc_recap`.)
5. **Richer carried outcome state** — tone is the first facet; do we carry
   more of the outcome (flags, relationship deltas) into continuation
   eligibility now, or leave the hook and add later? (Lean: leave the
   hook; wire tone first.)

## Action Items

Suggested as a phase (e.g. **Phase 25 — event taxonomy rework**),
sequenced to keep each step green:

1. [ ] **Engine: rename + reshape `EventType`.** `EventId → EventType` =
       `(domain, nature, possible_tones: frozenset[EventTone])`. Essence
       key for equality/registry = `(domain, nature)` (tone-set excluded);
       round-trip incl. the set. Compat shim for `taxonomy_id` on old saves.
2. [ ] **Registry.** `VALID_EVENT_COMBINATIONS` → `(domain, nature)` set;
       relax the Phase 19 coverage test to "≥1 blueprint per essence,"
       keep validity.
3. [ ] **Continuation matching.** `chains_from` / `_chain_bias` (and the
       arc-graph resume) match on **resolved tone vs candidate
       `possible_tones`** (soft), with domain/nature as optional bias —
       not essence-equality. Migrate `OutcomeRecord.taxonomy_id`; add
       `OutcomeRecord.resolved_tone`.
4. [ ] **Tone resolver.** `resolve_event_tone(event_type, *, carried_tone,
       context, rng)` — anchor = `possible_tones`, biased toward the
       carried target + context (morale / momentum / relationship / arc),
       drift to adjacent tones, chance tiebreak. Stamp the resolved tone on
       `OutcomeRecord`. Wire into `figure_layout_for` / `scene_intro`
       (replacing the static `event_id.tone` reads).
5. [ ] **Carry continuity.** Selection biases toward candidates whose
       `possible_tones` are compatible with the last outcome's resolved
       tone (soft); the chosen event then resolves its own tone (step 4),
       anchored on that carried target.
6. [ ] **Content overhaul.** Give every `EventType` a `possible_tones` set;
       ensure every `(domain, nature)` essence has ≥1 blueprint (cheaper
       now — one blueprint spans tones). Fold in the Phase 24E retones
       (`media_scrum`, `showing_off`) as plain edits.
7. [ ] **Tests.** EventType round-trip (incl. set); essence-equality
       ignores tone-set; resolved-tone continuity matching; resolver
       determinism + distribution (anchor-dominated, drift bounded);
       coverage/validity relaxation.
8. [ ] **Docs.** Update `CLAUDE.md` + `IMPLEMENTATION_PLAN.md`; supersede
       the in-code Phase 24E tone NOTEs.

**Coordination with item 1 (dynamic roles):** build the shared
`weighted_resolve` helper here and reuse it for participant-role
resolution, so the two features converge on one anchor + weighted-resolver
convention rather than two parallel ones.
