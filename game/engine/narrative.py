"""Narrative template system (design §7, technical §6).

Templates do the structural and factual work; the LLM (when enabled later)
rephrases a filled template for variety. The filled template is always the
fallback.

A template references slots with `{slot_name}`. Resolvers map slot names
to state-aware strings via `SLOT_RESOLVERS`. Resolvers receive a
`NarrationContext` — a small bundle of pre-computed fields so resolvers
don't need to walk the world.
"""

from __future__ import annotations

import random as _random
import re
from dataclasses import dataclass, field
from dataclasses import replace as replace_dataclass
from enum import Enum
from typing import Callable, Mapping, Sequence

from .characters import Character, TierACharacter
from .outcomes import OutcomeRecord
from .stats import ObservableName, StatName, StatTuple, clamp


# --- Temporal reference -----------------------------------------------------


class TemporalRef(str, Enum):
    """How far the template reaches back in story-time (design §7.1)."""

    NONE = "none"  # present moment only
    IMMEDIATE = "immediate"  # previous event's summary
    TRIGGER = "trigger"  # specific event that caused this one
    ARC = "arc"  # accumulated arc_summary


# --- Context bundle ---------------------------------------------------------


@dataclass
class NarrationContext:
    """Everything a resolver or template needs, pre-computed at narration time.

    Callers build this from `GameState` + the current `EventInstance` via
    `build_context()`. Kept small so template authors don't have to reason
    about the whole world.
    """

    # Cast
    target: Character | None = None  # primary speaker / focal character
    cast: dict[str, Character] = field(default_factory=dict)

    # History refs
    previous_outcome: OutcomeRecord | None = None
    trigger_outcome: OutcomeRecord | None = None
    arc_summary: str | None = None

    # Derived / scene-local
    composure: float = 0.5
    insecurity: float = 0.0
    confidence: float = 0.5
    mood: float = 0.0  # current team morale or personal mood delta
    location: str | None = None
    standout_action: str | None = None  # set by phase-sim hooks if relevant

    # Authored branch summary, when the narration is for a resolved event.
    branch_summary: str | None = None

    def tags(self) -> set[str]:
        """A compact tag set useful for template context_requirements."""
        tags: set[str] = set()
        if self.composure > 0.7:
            tags.add("composed")
        if self.insecurity > 0.6:
            tags.add("rattled")
        if self.confidence > 0.7:
            tags.add("confident")
        if self.mood > 0.2:
            tags.add("buoyant")
        if self.mood < -0.2:
            tags.add("bruised")
        if self.location:
            tags.add(f"loc:{self.location}")
        return tags


# --- Slot resolvers ---------------------------------------------------------


SlotResolver = Callable[[NarrationContext], str]


def _resolve_name(ctx: NarrationContext) -> str:
    if ctx.target is None:
        return "they"
    return ctx.target.nickname or ctx.target.name


def _resolve_prior(ctx: NarrationContext) -> str:
    if ctx.previous_outcome is None:
        return ""
    return ctx.previous_outcome.summary


def _resolve_trigger(ctx: NarrationContext) -> str:
    if ctx.trigger_outcome is None:
        # Graceful fallback to the immediate prior, as documented (§7.2).
        return _resolve_prior(ctx)
    return ctx.trigger_outcome.summary


def _resolve_arc(ctx: NarrationContext) -> str:
    if ctx.arc_summary:
        return ctx.arc_summary
    # Graceful fallback to the immediate prior.
    return _resolve_prior(ctx)


def _resolve_mood_descriptor(ctx: NarrationContext) -> str:
    if ctx.composure > 0.7:
        return "focused"
    if ctx.insecurity > 0.6:
        return "rattled"
    if ctx.confidence > 0.7:
        return "steady"
    if ctx.mood > 0.2:
        return "lifted"
    if ctx.mood < -0.2:
        return "heavy"
    return "quiet"


def _resolve_standout_action(ctx: NarrationContext) -> str:
    return ctx.standout_action or "made the play"


def _resolve_branch_summary(ctx: NarrationContext) -> str:
    summary = ctx.branch_summary or ""
    if "{" not in summary:
        return summary
    # Resolve slots authored into the summary (e.g. {they:player}) so
    # pronouns track gender here too. Blank branch_summary in the scoped
    # ctx so a stray {summary} can't recurse.
    return _substitute(summary, replace_dataclass(ctx, branch_summary=""))


# --- Pronoun resolvers ------------------------------------------------------
#
# Templates use {they}/{them}/{their}/{theirs}/{themself} (plus capitalised
# forms for sentence starts), role-scoped like {they:player}. Each reads the
# focal character's `gender_presentation` so narration matches the player's
# chosen presentation instead of defaulting to "he". Androgynous resolves to
# singular "they"; author such templates with plural-agreeing verbs.

_PRONOUN_TABLE: dict[str, dict[str, str]] = {
    "masculine": {
        "they": "he", "them": "him", "their": "his",
        "theirs": "his", "themself": "himself",
    },
    "feminine": {
        "they": "she", "them": "her", "their": "her",
        "theirs": "hers", "themself": "herself",
    },
    "androgynous": {
        "they": "they", "them": "them", "their": "their",
        "theirs": "theirs", "themself": "themself",
    },
}


# Pronoun-set labels for grounding the LLM (name → "she/her").
_PRONOUN_HINT: dict[str, str] = {
    "masculine": "he/him",
    "feminine": "she/her",
    "androgynous": "they/them",
}


def _pronoun(ctx: NarrationContext, key: str) -> str:
    """Look up a pronoun for the focal character's gender presentation."""
    gp = "masculine"
    if ctx.target is not None:
        gp = str(getattr(ctx.target, "gender_presentation", "") or "masculine")
    return _PRONOUN_TABLE.get(gp, _PRONOUN_TABLE["masculine"]).get(key, key)


def _make_pronoun_resolver(key: str, *, capitalise: bool) -> SlotResolver:
    def resolver(ctx: NarrationContext) -> str:
        word = _pronoun(ctx, key)
        return word[:1].upper() + word[1:] if capitalise else word

    return resolver


SLOT_RESOLVERS: dict[str, SlotResolver] = {
    "name": _resolve_name,
    "prior": _resolve_prior,
    "trigger": _resolve_trigger,
    "arc": _resolve_arc,
    "mood_descriptor": _resolve_mood_descriptor,
    "standout_action": _resolve_standout_action,
    "summary": _resolve_branch_summary,
}

# Register pronoun slots (lower-case + capitalised for sentence starts).
for _pkey in ("they", "them", "their", "theirs", "themself"):
    SLOT_RESOLVERS[_pkey] = _make_pronoun_resolver(_pkey, capitalise=False)
    SLOT_RESOLVERS[_pkey.capitalize()] = _make_pronoun_resolver(
        _pkey, capitalise=True
    )


def register_resolver(name: str, resolver: SlotResolver) -> None:
    """Extend the resolver table (for tests or content modules)."""
    SLOT_RESOLVERS[name] = resolver


# --- Template ---------------------------------------------------------------


# Template bodies use {slot} references. A slot references `.role` on the cast
# via the form {name:role} — optional, falls back to the target if absent.
_SLOT_PATTERN = re.compile(r"\{([a-zA-Z_][\w]*)(?::([a-zA-Z_][\w]*))?\}")


@dataclass
class NarrativeTemplate:
    id: str
    body: str
    temporal_reference: TemporalRef = TemporalRef.NONE
    context_requirements: set[str] = field(default_factory=set)
    base_weight: float = 1.0
    # Attachment: which event id or tag this template may render for.
    # Either `event_id` matches an EventBlueprint.id exactly, or any of
    # `event_tags` intersects the blueprint's tags.
    event_id: str | None = None
    event_tags: set[str] = field(default_factory=set)


# --- Filling ----------------------------------------------------------------


def _substitute(text: str, ctx: NarrationContext) -> str:
    """Resolve every `{slot}` / `{slot:role}` in *text* using `SLOT_RESOLVERS`.

    Role-scoped slots (`{name:coach}`, `{they:player}`) re-resolve against
    that cast member so pronouns track the right character's gender.
    Unknown slots render as `[slot]` so authoring errors are visible.
    """

    def replace(match: re.Match) -> str:
        slot = match.group(1)
        role = match.group(2)
        resolver = SLOT_RESOLVERS.get(slot)
        if role is not None:
            cast_char = ctx.cast.get(role)
            if cast_char is None or resolver is None:
                return f"[{slot}:{role}]"
            scoped = replace_dataclass(ctx, target=cast_char)
            return resolver(scoped)
        if resolver is None:
            return f"[{slot}]"
        return resolver(ctx)

    return _SLOT_PATTERN.sub(replace, text)


def fill_template(template: NarrativeTemplate, ctx: NarrationContext) -> str:
    """Substitute every `{slot}` in `template.body` using resolvers and cast.

    If a slot has a role suffix (`{name:coach}`) the role is looked up in
    `ctx.cast` first; otherwise the resolver receives the full ctx as-is.
    Unknown slots render as `[slot]` so authoring errors are visible.
    """
    return _substitute(template.body, ctx)


# --- Selection --------------------------------------------------------------


def _temporal_ok(template: NarrativeTemplate, ctx: NarrationContext) -> bool:
    ref = template.temporal_reference
    if ref is TemporalRef.NONE:
        return True
    if ref is TemporalRef.IMMEDIATE:
        return ctx.previous_outcome is not None
    if ref is TemporalRef.TRIGGER:
        return ctx.trigger_outcome is not None or ctx.previous_outcome is not None
    if ref is TemporalRef.ARC:
        return ctx.arc_summary is not None
    return True


def _reflective_boost(template: NarrativeTemplate, ctx: NarrationContext) -> float:
    """Arc-distance templates get weighted up for reflective characters (§7.1)."""
    if template.temporal_reference is not TemporalRef.ARC:
        return 1.0
    if not isinstance(ctx.target, TierACharacter):
        return 1.0
    refl = ctx.target.stats.get(StatName.REFLECTION)
    intro = ctx.target.stats.get(StatName.INTROSPECTION)
    refl_v = refl.value if isinstance(refl, StatTuple) else 0.5
    intro_v = intro.value if isinstance(intro, StatTuple) else 0.5
    # Blend: reflective + introspective character gets up to ~2x.
    return 1.0 + refl_v * 0.6 + intro_v * 0.4


def select_template(
    candidates: Sequence[NarrativeTemplate],
    ctx: NarrationContext,
    rng: _random.Random,
) -> NarrativeTemplate | None:
    """Weight-sample a template whose context_requirements are satisfied."""
    tags = ctx.tags()
    eligible = [
        t for t in candidates
        if t.context_requirements.issubset(tags) and _temporal_ok(t, ctx)
    ]
    if not eligible:
        return None
    weights = [t.base_weight * _reflective_boost(t, ctx) for t in eligible]
    if sum(weights) <= 0:
        return None
    return rng.choices(eligible, weights=weights, k=1)[0]


def templates_for_event(
    all_templates: Sequence[NarrativeTemplate],
    event_id: str,
    event_tags: set[str],
) -> list[NarrativeTemplate]:
    """Filter the template pool to those declaring attachment to this event."""
    out = []
    for t in all_templates:
        if t.event_id is not None and t.event_id == event_id:
            out.append(t)
            continue
        if t.event_tags & event_tags:
            out.append(t)
    return out


# --- Narrate ----------------------------------------------------------------


PAGE_MAX_CHARS = 280


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def paginate(text: str, max_chars: int = PAGE_MAX_CHARS) -> list[str]:
    """Split a narration string into screen-sized pages.

    Pages are packed greedily up to ``max_chars`` on sentence boundaries
    (`. ! ?` followed by whitespace). Paragraph breaks (`\\n\\n`) are
    treated as hard page boundaries. A run-on with no sentence boundary
    is word-wrapped so no page exceeds the cap. Empty input yields a
    single empty page so callers can iterate uniformly.
    """
    text = text.strip()
    if not text:
        return [""]

    pages: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        sentences = _SENTENCE_END.split(paragraph)
        current = ""
        for sentence in sentences:
            if not sentence:
                continue
            if len(sentence) > max_chars:
                # Flush current page, then word-wrap the long sentence.
                if current:
                    pages.append(current)
                    current = ""
                pages.extend(_wrap_words(sentence, max_chars))
                continue
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) > max_chars:
                pages.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            pages.append(current)
    return pages or [""]


def _wrap_words(text: str, max_chars: int) -> list[str]:
    """Word-wrap a long run-on into chunks no larger than ``max_chars``."""
    out: list[str] = []
    current = ""
    for word in text.split():
        if len(word) > max_chars:
            if current:
                out.append(current)
                current = ""
            # A single token longer than the cap — hard-slice it.
            for i in range(0, len(word), max_chars):
                out.append(word[i : i + max_chars])
            continue
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) > max_chars:
            out.append(current)
            current = word
        else:
            current = candidate
    if current:
        out.append(current)
    return out


def narrate(
    templates: Sequence[NarrativeTemplate],
    ctx: NarrationContext,
    rng: _random.Random,
    *,
    use_llm: bool = False,
    llm_client: "LLMClient | None" = None,
    event_tags: set[str] = frozenset(),
    max_chars: int = PAGE_MAX_CHARS,
) -> list[str]:
    """Pick a template and return the filled narration as a list of pages.

    Falls back to `ctx.branch_summary` if no template matches — every event
    has one as a last-resort narration.

    When ``use_llm`` is True and an ``llm_client`` is provided, high-drama
    events get their filled template rephrased by the LLM. The filled
    template is always the fallback.

    The result is paginated via :func:`paginate` so long template fills
    (descriptor-heavy) and LLM-rephrased outputs both split cleanly across
    screens. Short narration yields a single-page list.
    """
    template = select_template(templates, ctx, rng)
    if template is None:
        # No template — resolve slots authored into the summary itself so
        # the last-resort narration still gets gendered pronouns.
        filled = _resolve_branch_summary(ctx)
    else:
        filled = fill_template(template, ctx)

    if use_llm and llm_client is not None:
        from .llm import enhance_narration

        cast_names = [
            c.nickname or c.name
            for c in ctx.cast.values()
            if hasattr(c, "name")
        ]
        cast_pronouns = {
            (c.nickname or c.name): _PRONOUN_HINT.get(
                str(getattr(c, "gender_presentation", "") or "masculine"),
                "they/them",
            )
            for c in ctx.cast.values()
            if hasattr(c, "name")
        }
        filled = enhance_narration(
            llm_client,
            filled,
            event_tags=event_tags,
            arc_summary=ctx.arc_summary,
            previous_summary=(
                ctx.previous_outcome.summary if ctx.previous_outcome else None
            ),
            cast_names=cast_names,
            branch_summary=ctx.branch_summary,
            location=ctx.location,
            cast_pronouns=cast_pronouns,
        )

    return paginate(filled, max_chars=max_chars)


# --- Arc summary compression ------------------------------------------------


ARC_SUMMARY_MAX_CHARS = 320


def compress_arc_summary(summary: str, max_chars: int = ARC_SUMMARY_MAX_CHARS) -> str:
    """Truncate a digest-appended arc summary at a sentence boundary.

    Keeps the most recent portion (the head of the summary chain is older
    and less load-bearing for continuity). The chain is appended newest-last
    via `OutcomeRecord` resolution, so we slice from the right.
    """
    if len(summary) <= max_chars:
        return summary
    tail = summary[-max_chars:]
    # Find a sentence boundary in the first 40 chars of the tail; otherwise use
    # the first space to avoid cutting a word in half.
    head_window = tail[:60]
    period = head_window.find(". ")
    if period != -1:
        return tail[period + 2 :]
    space = head_window.find(" ")
    if space != -1:
        return tail[space + 1 :]
    return tail


# --- Context construction ---------------------------------------------------


def build_narration_context(
    *,
    target: Character | None = None,
    cast: Mapping[str, Character] | None = None,
    outcome_log: Sequence[OutcomeRecord] = (),
    trigger_outcome: OutcomeRecord | None = None,
    team_morale: float = 0.0,
    location: str | None = None,
    standout_action: str | None = None,
    branch_summary: str | None = None,
) -> NarrationContext:
    """Assemble a NarrationContext from state pieces.

    `previous_outcome` is derived from the log; `arc_summary` pulls from the
    most recent outcome that carried one.
    """
    previous = outcome_log[-1] if outcome_log else None

    arc_summary = None
    for o in reversed(outcome_log):
        if o.arc_summary:
            arc_summary = o.arc_summary
            break

    composure = 0.5
    insecurity = 0.0
    confidence = 0.5
    if target is not None:
        composure = _safe_observable(target, ObservableName.COMPOSURE)
        if isinstance(target, TierACharacter):
            insecurity = target.insecurity()
        conf_raw = target.stats.get(StatName.CONFIDENCE)
        if isinstance(conf_raw, StatTuple):
            confidence = conf_raw.value
        elif isinstance(conf_raw, (int, float)):
            confidence = float(conf_raw)

    return NarrationContext(
        target=target,
        cast=dict(cast or {}),
        previous_outcome=previous,
        trigger_outcome=trigger_outcome,
        arc_summary=arc_summary,
        composure=clamp(composure),
        insecurity=clamp(insecurity),
        confidence=clamp(confidence),
        mood=team_morale,
        location=location,
        standout_action=standout_action,
        branch_summary=branch_summary,
    )


def _safe_observable(char: Character, obs: ObservableName) -> float:
    try:
        return char.observable(obs)
    except Exception:
        return 0.5


# --- Match phase narration (Phase 22F) ---------------------------------------
#
# Turns a PhaseResult into a narrated line instead of a stat readout.
# Pure and rng-injected like everything else in the engine; Ren'Py gets
# the finished string via ``GameSession.narrate_match_phase``.

_GOAL_LINES = (
    "GOAL! {scorer} picks the moment and buries it.",
    "It falls to {scorer} — and {scorer} doesn't miss those. GOAL!",
    "GOAL! {scorer} finishes what the whole move deserved.",
    "{scorer} arrives exactly on time and turns it in. GOAL!",
)

_DOMINATING_LINES = (
    "Your side has the game by the collar; {opponent} can't keep the ball "
    "for thirty seconds at a stretch.",
    "Wave after wave — {opponent} are defending the box like it owes them "
    "money.",
    "Everything is happening in {opponent}'s half. The pressure has a "
    "rhythm to it now.",
)

_PRESSURE_LINES = (
    "{opponent} turn the screw. The back line is doing all of the talking "
    "and most of the running.",
    "Long spells without the ball. {opponent} keep finding the same gap "
    "and everyone on the pitch knows it.",
    "It's all hands behind the ball — {opponent} are queuing up shots.",
)

_EVEN_LINES = (
    "Trench warfare in midfield — neither side will give the first yard.",
    "The game is even and angry about it; every loose ball gets three "
    "challenges.",
    "Tight as a held breath. One mistake either way decides this spell.",
)

_LATE_SURGE_LINES = (
    "Legs are heavy, but the momentum is yours and the whole ground can "
    "feel it.",
    "Late in the day, and your side keep coming — {opponent} just want to "
    "hear the whistle.",
)

_LATE_FADE_LINES = (
    "The clock is becoming a problem. {opponent} can smell it.",
    "Tired legs, tired minds — {opponent} are winning every second ball "
    "now.",
)

# Performance gap (team − opponent) beyond which a phase reads as
# one-sided rather than even.
PHASE_GAP_THRESHOLD = 0.12
# |momentum| beyond which a late phase reads as a surge/fade.
LATE_MOMENTUM_THRESHOLD = 0.25


def narrate_match_phase(
    result: "PhaseResult",
    rng: _random.Random,
    *,
    scorer_name: str | None = None,
    opponent_name: str = "the opposition",
    phase_index: int = 0,
    total_phases: int = 8,
) -> str:
    """One narrated line for a simulated match phase.

    Goal phases name the scorer; otherwise the line reads the balance of
    play, with late-game variants when momentum is pronounced.
    """
    if result.goal_scored:
        line = rng.choice(_GOAL_LINES)
        return line.format(scorer=scorer_name or "Someone", opponent=opponent_name)

    late = total_phases > 0 and phase_index >= int(total_phases * 0.75)
    if late and result.momentum >= LATE_MOMENTUM_THRESHOLD:
        pool = _LATE_SURGE_LINES
    elif late and result.momentum <= -LATE_MOMENTUM_THRESHOLD:
        pool = _LATE_FADE_LINES
    elif result.team_perf - result.opp_perf > PHASE_GAP_THRESHOLD:
        pool = _DOMINATING_LINES
    elif result.opp_perf - result.team_perf > PHASE_GAP_THRESHOLD:
        pool = _PRESSURE_LINES
    else:
        pool = _EVEN_LINES
    return rng.choice(pool).format(opponent=opponent_name)


_SELF_EVAL_BANDS: tuple[tuple[float, tuple[str, ...]], ...] = (
    (0.70, (
        "You walk off feeling like you ran the game.",
        "Whatever else happened out there, you know you delivered.",
    )),
    (0.55, (
        "You did your job today, and you know it.",
        "A solid shift. Nothing to apologise for.",
    )),
    (0.40, (
        "You can't quite decide what kind of game you had.",
        "Bits of it were good. You keep returning to the other bits.",
    )),
    (0.0, (
        "Whatever the table says, it feels like you let it slip.",
        "You replay your touches on the walk in, and none of them improve.",
    )),
)


def self_evaluation_line(perceived: float, rng: _random.Random) -> str:
    """Narrated self-evaluation for the post-match summary.

    ``perceived`` is the awareness-filtered self-rating from
    ``self_evaluate`` — deliberately *not* the actual performance, so
    the line can contradict the scoreline for low-awareness players.
    """
    for cutoff, lines in _SELF_EVAL_BANDS:
        if perceived >= cutoff:
            return rng.choice(lines)
    return _SELF_EVAL_BANDS[-1][1][0]
