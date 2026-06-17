# Narrative flow

## Player presence

- Player character always implicitly present
  - Could have variable role, such as spectator/onlooker, actor, reactor etc.
  - Narration should take into consideration how the main character reacts to the scene
- Player role should affect the possible decisions to make, not just the player personality

## Event narration

- Event narration should receive as context/conversation history the prior narrative output to ensure continuity. Periodic summary to compress conversation history
  - Summarize at scene boundaries to indicate the trigger, description, player reaction and outcome as a single paragraph
  - Summarize at transition to new day to provide a detailed summary of the day as a whole
  - Summarize at week transitions to provide a detailed summary of the week as a whole
- Event roles should be relatively persistent, but allowing them to change as result of actions could provide an avenue for narration.
- An event should consist of more than just "Presentation+Choice"
  - If scene change, present scene
  - Narrate event setup. Split paragraphs across multiple screens on demand
    - Will require just-in-time llm resolution of event setup before scheduling the event screens
  - Present choices
  - Narrate player action
  - Narrate outcome/reaction (separate screen)
  - Narrate event result
  - Move to new event and possibly new scene

## Visual composition & cast (hooks from the rendering work)

The background + figure rendering is built; these are the narrative-side
levers it exposes, to drive during this pass.

- **Figure proximity is authorable but unused.** `FigureDistance`
  (INTIMATE / CLOSE / NORMAL / DISTANT) is wired through
  `session.figure_layout_for` (drives NPC scale, spacing, overlap) but
  every scene defaults to NORMAL. Add a per-event / per-role **distance
  cue** — intimate confession sits close, a formal confrontation sits
  distant. `EventTone.ROMANTIC → INTIMATE` is the obvious first mapping.
  (`engine/figure_layout.py`, `engine/figures.py`.)
- **Figure posture already follows `event_id.tone`** — interlocutor
  warm/neutral/tense, authority comforting/sceptical/angry — via
  `figures.posture_for`. So events need accurate tones; audit them in
  this pass. Consider letting tone (→ posture) **shift within an event**
  as choices land (a sceptical coach turns angry) — ties to the "roles
  can change as a result of actions" point above.
- **Escalating cast (2 → 3 → 4).** The visual layer supports adding
  figures mid-scene (overlap caps + a join/leave peripheral figure).
  Model the growth as **event chains that pin the prior cast forward**
  (`cast_event(pinned=...)`, already used for match beats) and add an
  optional role — "the rival's mate wanders over" = a chained event with
  `[player, rival]` pinned + a new `mate`. One small engine helper is
  needed: carry the prior cast into the chained event (chains currently
  re-cast fresh). Continuity rides `OutcomeRecord.arc_summary`.
- **Player presence maps to figure framing.** The "variable role"
  (spectator / onlooker / actor / reactor) can drive the player's
  from-behind anchor: actor = foreground (default), spectator = further
  back / smaller / aside, or omitted for a pure first-person beat. Decide
  per-event how present the MC silhouette is.
- **Appearance is persisted + consistent.** Every character carries a
  `CharacterDescriptor` (gender, skin, hair, age); figure selection is
  deterministic from it, so narration may safely reference loose
  appearance ("the blonde striker") and it stays matched to the rendered
  figure across scenes.

## Continuity & LLM (build on what's shipped, don't reinvent)

- **Pronouns:** narration is third-person past tense using role-scoped
  pronoun slots (`{they:player}`, `{their:mentor}`); never hardcode
  he/she. `{summary}` resolves slots recursively.
  `scripts/check_summary_pronouns.py` guards new summaries.
- **One continuity mechanism.** The "prior narrative output as
  conversation history + periodic summaries" idea overlaps the existing
  `arc_summary` digest-append chain. Reconcile them into a single
  mechanism rather than running two — the scene/day/week summaries can be
  the compression layer on top of the per-event arc digest.
- **LLM grounding already exists.** `enhance_narration` grounds the model
  with location, cast pronouns, arc summary, and previous outcome (model
  `liquid/lfm2-24b-a2b`, reasoning-block stripping, silent
  template/assembled fallback). The richer event structure (setup →
  choice → action → outcome → result, multi-screen) should extend this
  path, and JIT setup resolution should keep the **never-block,
  always-fallback** discipline (filled template / engine-assembled text
  is the fallback; the game never waits on the LLM).
- **Scene intro is engine-assembled + LLM-polished** already
  (`session.scene_intro`: place + company + tone line, rephrased). The
  "narrate event setup, split across screens" step builds on this, not
  from scratch.

## Content / authoring hooks (surfaced during rendering)

- **`valid_scene_types` order is the resolution lever.** The first type
  that maps to a baked spec wins, so several scene types are *shadowed*
  (e.g. injury → locker room because `locker_room` precedes `medical`).
  When authoring events this pass, reorder to promote a more fitting
  background where wanted. (See `field_and_heart_prebake_rendering.md`
  Appendix D.)
- **Backgrounds without events = authoring opportunities.** Baked/planned
  locations with no events to use them: mansion (wealth disparity / agent
  / sponsor), sauna / pool / lakeside (recovery, vulnerability, bonding),
  kiosk / grocery (chance encounters — `personal.kind_stranger` fits),
  stadium exterior / showers. Good candidates for new event chains.
- **Some baked figure categories aren't composited yet.** Today only the
  drama / postgame blocks call `show_figures`; the **motion** (in-match)
  and **anonymous** (locker/shower) figure categories are baked but
  unused. Wire `show_figures` into the match beats and any
  locker-room/shower scenes if those should show figures.
- **Match in-phase beats** (`select_match_event` / `goal_huddle`) are
  text + choice today, no figure composite — a natural place to extend
  once motion figures land.
