# Design: Face-less Painterly Figure Assets

Status: **proposed** (catalogue; spike to follow)
Date: 2026-06-16
Companion to `field_and_heart_prebake_rendering.md` (backgrounds).

## Goal & philosophy

Add character presence without solving identity preservation. Figures
are **abstract, expressive, face-less** painterly forms composited over a
background — flavour and immersion, not portraiture. **The text does the
storytelling**; figures set the scene.

- **No faces, no fine detail.** A deliberate negative prompt
  (`face, facial features, eyes, portrait, close-up, identifiable
  person, detailed hands`) removes the hardest-to-get-right, most
  uncanny, identity-locked parts.
- **Loose specification = reuse.** A figure tagged only by coarse axes
  (gender, skin light/dark, hair colour/length) can plausibly be the
  opposing striker *and* the café regular. Never make one specific.
- **Variety over fidelity.** ~150 small assets; coverage and permutation
  do more for perceived quality than per-figure polish. More
  permutations → less frequent reuse → less "haven't I seen them?".

## Asset model

A **figure overlay layer** in the existing `scene_compose` stack —
architecturally a sibling of background *alternates*, not the per-
character composite path:

- Each asset is a painterly figure (or posed pair) on a plain/neutral
  field, matted to a transparent foreground at bake time.
- Selected per event from the cast's tracked appearance + the event's
  tone; drawn over the resolved background.
- **Player** = a foreground silhouette/outline anchor (representation
  TBD — decide from the spike).

## Appearance axes (reuse `CharacterDescriptor`, already in the engine)

`sprite_pool.CharacterDescriptor` already carries every axis we need —
`gender_presentation`, `age_bucket`, `skin_tone`, `build`, `hair`
(length+colour token), `facial_hair`, `glasses` — and
`character_factory.random_descriptor` already rolls them.

**The one required engine change: persist the descriptor on characters.**
✅ **Done (June 2026).** `TierACharacter` / `TierBCharacter` now carry
`descriptor: CharacterDescriptor | None`, round-tripped in `to_dict` /
`from_dict` (and therefore `save.py`); `generate_character` stores the
descriptor it already rolled instead of discarding it; legacy saves
without the field load as `None`. Figure selection can now map
`(descriptor → nearest figure appearance) + (event tone → posture)`, so
the blonde striker stays blonde wherever she appears.

Figure appearance grid (coarse on purpose):

| Axis | Values | Count |
|------|--------|-------|
| gender | masculine / feminine | 2 |
| skin | light / dark | 2 |
| hair colour | dark / light / red | 3 |
| hair length | short / long | 2 |
| age | adult / older (where it matters) | 2 |

Base appearance grid = gender × skin × hair-colour × hair-length = **24**
distinct people; age applied selectively. Androgynous reuses the nearest
(lean choice). NPC descriptors snap to the nearest grid cell.

## Posture / tone vocabulary

Conversation figures read their stance from the event's `EventTone`
(already on every `event_id`), so selection is automatic:

- **Interlocutor** postures: open/warm, neutral, closed/tense.
- **Authority** (manager + senior roles) posture set:
  cheering/comforting, condescending/angry, questioning/sceptical.
  (Some other roles can reuse this set.)

## Catalogue (~150)

Variety is concentrated on **interlocutors** (where reuse hurts most);
anonymous and specialist figures stay lean.

| Category | Axes | Count | Covers |
|---|---|---|---|
| **Conversation interlocutors** | 24 appearances × 2 postures (open/warm, closed/tense) | ~48 | the 37 two-figure drama/social events |
| **Authority / manager** | gender(2) × age(2) × skin(2) × posture(3) | ~24 | coach/mentor/official/manager roles; reusable across office/pitch/conference |
| **Practice / match** (in motion, anonymous) | sport(3) × gender(2) × action(3: run, contact, shoot/celebrate) | ~18 | match block, training/sport |
| **Service staff** | role(3: waiter, cashier, vendor) × gender(2) × skin(2) | ~12 | café/restaurant/kiosk/downtime |
| **Medical staff** (nurse, doctor) | role(2) × gender(2) × skin(2) | ~8 | physio/medical/injury |
| **Office worker** (generic) | gender(2) × skin(2) | ~4 | institutional/admin |
| **Locker room / showers** (anonymous) | gender(2) × pose(2) × skin(2) | ~8 | locker_room, showers |
| **Player silhouette** | gender(3) × context(2: kit, casual) | ~6 | POV anchor (pending spike) |
| **Objects / props** | door, shower fixture, ball, kit bag, bench, whiteboard, cup, phone | ~8 | interaction flavour |
| **Total (pre-spike)** | | **~136** | headroom to ~150 via extra interlocutor postures / hair colours |

Far more reusable than backgrounds: one authority set serves every
coach/official scene; the 24-appearance interlocutor pool serves dozens
of events. Count is efficient despite the variety.

## Integration sketch

- New figure overlay layer; selection keyed off `(cast descriptor,
  event tone)`. Single-figure events → interlocutor (+ optional player
  silhouette); solo → silhouette only; match → players-in-motion;
  service/medical/authority → archetype by cast role.
- Composited above the background, below grades/overlays, via the
  existing `scene_compose` ATL stack — no new display plumbing.
- Bake pipeline mirrors backgrounds: a manifest-driven driver, the same
  painterly recipe **plus the face-less negative prompt**, matted to
  transparency. Reuse `prebake_assets.py` patterns.

## Spike plan (representative)

Validate the look before committing ~150. Spread across the trickiest
cases: anonymity, posture-reads-tone, appearance variety reading as
different people, motion, specialist dress, the silhouette concept.

1. Interlocutor — feminine, dark skin, long dark hair, **warm/open**.
2. Interlocutor — masculine, light skin, short blonde hair, **closed/tense**.
3. Manager — masculine, older, **condescending/angry**.
4. Manager — feminine, adult, **cheering/comforting**.
5. Player-in-motion — soccer, feminine (running/contact).
6. Medical — doctor, feminine.
7. Service — waitress.
8. Player silhouette — to judge the POV-anchor concept.

Generated on a neutral field (matting to transparency is an integration
step, not a quality question). Judge: does face-less read as expressive
rather than eerie? Do the appearance axes read as distinct people? Does
posture convey tone without a face?

## Spike verdict & locked recipe (June 2026)

Two spike passes (8 + 4 figures). v1 confirmed the concept reads but
front-facing/action poses (soccer player, angry manager) leaked rendered
faces and the style was a touch photographic. v2 fixed both.

**Decisive finding: face protection is a *framing* lever, not just a
negative prompt.** "Seen from behind / head turned away / profile" in the
prompt is what reliably removes the face; the negative alone doesn't stop
a front-facing pose. The heavier impressionistic style then dissolves any
residual facial detail into brushwork.

**Locked figure recipe** (to bake into the figure producer):

- **Style:** `very loose impressionistic oil painting, abstract gestural
  brushwork, palette-knife strokes, simplified blocky forms, soft blurred
  edges, the figure suggested rather than detailed, face dissolved into
  loose brushstrokes, seen from behind or in profile with head turned
  away, anonymous, muted palette, plain neutral background, alla prima`
- **Negative:** `face, facial features, eyes, mouth, nose, portrait,
  close-up, looking at viewer, front view, facing camera, detailed face,
  rendered face, identifiable person, sharp focus, fine detail, crisp
  lines, detailed hands, photorealistic, photograph, 3d render, cgi,
  pixel art, text, watermark, deformed, extra limbs`
- **Per-figure:** add `seen from behind` (or `running away`) to any pose
  that would otherwise face the viewer (action, pointing, etc.).
- Same sampler/steps as backgrounds (euler/sgm_uniform, ~34 steps,
  cfg 4.5); portrait field 832×1216.

**Consequence for the catalogue — posture must read from behind/profile.**
Tone is carried by body language (crossed arms, open arms, pointing,
leaning, slumped), never facial expression. Conversation figures lean
**profile / three-quarter turned-away**; action and anonymous figures
lean **from-behind**. The authority posture set (cheering/comforting,
condescending/angry, questioning/sceptical) must each be legible as a
silhouette of body language.

**Player silhouette concept validated** (v1 #8): a clean painterly
silhouette reads well as a POV anchor — favours the "foreground
silhouette" option, though final call still pending in-scene composition.

## Framing model — RESOLVED (June 2026, v3 spike)

Three spike passes settled the look. The two framings have distinct jobs;
composited together they give the third-person over-the-shoulder view:

- **NPCs → frontal Disco-Elysium-style painted sketch.** Faces *present
  but impressionistic* (loose oil-and-ink, gestural linework, soft
  indistinct features). Frontal is fine — abstraction, not framing,
  carries anonymity, and we get facial-cue tone as a bonus on top of
  posture. v3 verdict: strong; the inkier/sketchier renders (folded-arms
  manager, crossed-arms man) are the target; smoother faces can be
  pushed looser if drift is a concern.
- **Player → from-behind figure / silhouette** (v2 recipe) as the
  foreground POV anchor, lower-corner, back to camera.
- **Compose:** player back foreground-left + NPC frontal mid-ground =
  third-person scene. v2's from-behind work is the player layer, not
  wasted.

**Locked NPC (frontal) recipe:**

- **Style:** `Disco Elysium style painted character study, loose oil and
  ink sketch, thick visible brushstrokes, gestural sketchy linework,
  impressionistic abstracted face with soft indistinct blurred features,
  unfinished painterly sketch, muted desaturated palette, moody, full
  body, plain muted background`
- **Negative:** `photorealistic, photograph, smooth skin, sharp focus,
  detailed eyes, detailed rendered face, glamour, beauty shot, anime,
  cartoon, clean lines, 3d render, cgi, pixel art, text, watermark,
  deformed, extra limbs, extra fingers`
- Tone via posture **and** loose facial cue; euler/sgm_uniform, ~34
  steps, cfg 4.5, portrait 832×1216.
- **Gaze / facing (composition):** the player sits foreground-**left**,
  back to camera, angled **right** into the scene. So NPCs must look
  **toward the viewer's lower-left** (toward the MC) — add
  `looking toward the lower left, gaze to the side` to the NPC prompt and
  `seen from behind, angled to the right` to the player prompt. This
  sells "they're looking at the MC."
- **Player layer** keeps the v2 from-behind recipe (+ angled-right gaze).
- **Coverage:** the bake must cover **both genders per category,
  including the player** — selection degrades a missing exact appearance
  but cannot invent a gender that wasn't baked (the stub initially had
  only a male player, so a female MC rendered male until `player_f` was
  added).

## Concerns resolved (June 2026)

### Escalating cast (2 → 3 → 4)

Two fixes, two layers:

- **Narrative:** model as event **chains** where each step pins the prior
  cast forward (reuse `cast_event(pinned=...)` from 22F) and adds one
  `RoleSlot`. Continuity already rides `arc_summary`. One engine gap to
  close: a "carry prior cast into the chained event" helper, since chains
  currently re-cast fresh. Then "the rival's mate wanders over" = a
  chained event with `[player, rival]` pinned + a new `mate` role.
- **Assets:** never bake distinct 2/3/4-person group scenes
  (combinatorial). A group *grows by adding figure layers* — a small set
  of generic **join/leave peripheral figures** (silhouette/shadow at the
  frame edge, waving in / leaning away; one asset can serve both
  directions to start), composited on top.

### State-driven role variants

Confirmed: **fresh txt2img per variant, not img2img.** img2img would
fight to preserve the very detail we deliberately don't render;
abstraction is what prevents identity drift, so it earns its keep. Each
variant (e.g. manager comforting / angry / sceptical) = its own txt2img
with the same coarse appearance tags + a different posture, fixed seed
per `(appearance, posture)` so variants stay siblings. The figure layer
selects the variant from `(role/character, state)` — manager stance from
morale / recent result, or an event-authored tone.

## Matting + composite — RESOLVED (June 2026)

Proof run (`scripts/composite_test.py`): `rembg` (u2net) cuts the
painterly figures cleanly — including the **hard case** (frontal NPC on a
muted cream field) and wispy hair — to transparent PNGs, then a
from-behind player anchor + frontal NPC composited over a real baked
background read as a coherent third-person over-the-shoulder scene. The
figure and background styles cohere because both come from the same
painterly recipe family.

- **`rembg` is a bake-time tool, not a runtime dependency.** Matting
  happens once in the figure bake driver; shipped assets are pre-matted
  transparent PNGs. The runtime just `alpha_composite`s them — no new
  runtime dep, fits the existing `scene_compose` stack.
- Whole figure layer now de-risked: look locked, matte clean, composite
  validated.

## Build order / progress

1. **Persist `CharacterDescriptor` on characters.** ✅ Done.
2. **Figure data model + selection.** ✅ Done — `engine/figures.py`:
   `FigureCategory` / `FigurePosture` / `FigureAppearance` / `FigureAsset`
   / `FigureManifest`, plus `appearance_from_descriptor`,
   `posture_for(category, tone)`, `category_for_role(role, in_match=)`,
   and `select_figure` (scored nearest-match — gender + posture dominate,
   appearance axes degrade gracefully, always returns something
   in-category). `select_for_character` ties it together. 13 tests.
   Headless; no assets needed yet.
3. **Figure bake driver.** ✅ Built — `scripts/figure_bake.py`.
   - Enumerates **126** assets: interlocutors 56 (full 24-grid × warm/
     tense + 8 neutral), authority 32 (gender×skin×age×4 postures),
     service/medical/office 4 each, player 16 (from-behind, both
     genders), motion 6, anonymous 4. Both genders per category.
   - Frontal DE recipe + lower-left gaze for NPC categories; from-behind
     recipe for player/motion/anonymous. `rembg` matte to transparency.
     Writes `game/assets/figures/<category>/…` + `figures.json`.
   - Idempotent (stable path + hashlib seed; skips on-disk); `--dry-run`
     / `--only <category>` / `--placeholder` (no GPU) / `--force`.
   - Validated via `--placeholder` (enumeration, subdir layout, manifest,
     idempotency). Real bake pending — needs ComfyUI on :8000.
   - **Before the real bake:** `rm -rf game/assets/figures` to drop the
     stub so `figures.json` starts clean. ~126 × (~140s gen + matte) ≈
     5 h; run `--only interlocutor` etc. to bake in stages, or resume
     (idempotent) if interrupted.
4. **Composite layer.** ✅ Done.
   - `engine/figure_layout.py`: pure geometry honoring the authored
     constraints — dynamic horizontal `closeness` with overlap caps
     (normal ~25% heads-visible, `intimate` up to ~75%), **static
     vertical baseline** for standing figures, and **enter/exit
     downscale anchored chest-at-1/3-from-top**. Player = large
     foreground anchor cropped below frame; NPCs mid-ground facing them.
     9 tests.
   - `GameSession.figure_layout_for(blueprint, cast, w, h, …)` ties
     selection + geometry: per cast member → `select_for_character`
     (descriptor + tone), player → from-behind PLAYER asset; returns
     `(path, box, role)` NPCs-first then player (drawn on top). Skips
     cast with no available asset; `[]` if no pack. 2 session tests.
   - `scene_compose.rpy`: `show_figures` / `hide_figures` composite the
     matted images over the background via `_fh_image` + a Transform per
     box (player higher z-order). Wired into `drama_block` /
     `postgame_block`, replacing the old `show_character` stub.
   - **Stub pack** (`scripts/figure_stub.py`): mattes 4 spike figures to
     `game/assets/figures/` + `figures.json` so the composite shows
     in-game before the real bake. Verified: events resolve player +
     interlocutor, gender-dominates-posture degradation visible.
   - **Proximity** is a named `FigureDistance` enum —
     **INTIMATE / CLOSE / NORMAL / DISTANT** — driving NPC scale (depth
     cue), horizontal closeness, and the overlap cap together. Default
     NORMAL; **event roles will cue the level** (a narration/progression
     review is planned anyway). Animating the transition across scene
     changes (ATL tween) remains a future hook.
   - Figure heights were **downscaled ~10%** (player was clipping the top
     edge; figures read too large over some backgrounds). Constants at
     the top of `figure_layout.py`.
5. **Author + bake** the full catalogue; iterate.

The bake driver (3) is the remaining big piece; the composite (4) runs
now against the stub pack.

## Open questions

1. ~~Player representation~~ — **resolved:** from-behind figure /
   silhouette as foreground POV anchor (see Framing model).
2. ~~Transparency / matting~~ — **resolved:** `rembg` at bake time (see
   above).
3. **Own-vs-opposing team** — runtime kit-colour tint (cheap) vs separate
   art. Lean: tint.
4. **Face looseness dial** — smoother frontal faces (the women in v3) can
   be pushed inkier/vaguer if identity drift bites; per-taste, not
   blocking.
5. **Single figures vs posed pairs** — start single (player silhouette +
   frontal NPC compose the pair; extra people via join/leave edge
   layers); author true pairs only if composition reads awkwardly.
