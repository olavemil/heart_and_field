import random
from pathlib import Path

import pytest

from engine.characters import CharacterRole, TierACharacter, TierBCharacter
from engine.content_loader import (
    load_blueprints_from_path,
    load_templates_from_path,
)
from engine.events import cast_event, resolve_outcome
from engine.narrative import (
    NarrationContext,
    NarrativeTemplate,
    SLOT_RESOLVERS,
    TemporalRef,
    build_narration_context,
    compress_arc_summary,
    fill_template,
    narrate,
    select_template,
    templates_for_event,
)
from engine.outcomes import OutcomeRecord, WeekPhase
from engine.stats import StatName, StatTuple


# --- Helpers ----------------------------------------------------------------


def _tuple(v: float, awareness: float = 0.6, focus: float = 0.4) -> StatTuple:
    return StatTuple(value=v, awareness=awareness, focus=focus)


def make_player(**overrides) -> TierACharacter:
    stats = {s: _tuple(0.5) for s in StatName}
    for k, v in overrides.items():
        stats[k] = v
    return TierACharacter(
        id="player",
        name="Alex",
        nickname="Al",
        role=CharacterRole.STRIKER,
        stats=stats,
    )


def make_coach() -> TierBCharacter:
    return TierBCharacter(
        id="coach",
        name="Boaz",
        role=CharacterRole.MANAGER,
        stats={s: 0.6 for s in StatName},
    )


# --- Resolvers & fill -------------------------------------------------------


def test_name_uses_nickname_when_set():
    player = make_player()
    ctx = NarrationContext(target=player)
    assert SLOT_RESOLVERS["name"](ctx) == "Al"


def test_name_falls_back_to_full_name():
    player = make_player()
    player.nickname = None
    ctx = NarrationContext(target=player)
    assert SLOT_RESOLVERS["name"](ctx) == "Alex"


def test_mood_descriptor_branches():
    ctx = NarrationContext(composure=0.9)
    assert SLOT_RESOLVERS["mood_descriptor"](ctx) == "focused"
    ctx = NarrationContext(composure=0.3, insecurity=0.7)
    assert SLOT_RESOLVERS["mood_descriptor"](ctx) == "rattled"
    ctx = NarrationContext(confidence=0.8)
    assert SLOT_RESOLVERS["mood_descriptor"](ctx) == "steady"


def test_arc_falls_back_to_prior_when_unset():
    prior = OutcomeRecord(
        event_id="e",
        timestamp=WeekPhase(1, 1),
        participants={},
        branch_taken="x",
        summary="He lost it.",
    )
    ctx = NarrationContext(previous_outcome=prior, arc_summary=None)
    assert SLOT_RESOLVERS["arc"](ctx) == "He lost it."


def test_fill_template_substitutes_role_scoped_name():
    player = make_player()
    coach = make_coach()
    tpl = NarrativeTemplate(
        id="t",
        body="{name:player} listened to {name:coach}.",
    )
    ctx = NarrationContext(
        target=player,
        cast={"player": player, "coach": coach},
    )
    assert fill_template(tpl, ctx) == "Al listened to Boaz."


def test_fill_unknown_slot_renders_bracketed_marker():
    tpl = NarrativeTemplate(id="t", body="Hello {mystery}.")
    ctx = NarrationContext()
    assert fill_template(tpl, ctx) == "Hello [mystery]."


def test_fill_unknown_role_renders_bracketed_marker():
    tpl = NarrativeTemplate(id="t", body="{name:ghost} appeared.")
    ctx = NarrationContext(target=make_player(), cast={"player": make_player()})
    assert fill_template(tpl, ctx) == "[name:ghost] appeared."


def test_fill_summary_slot_passes_branch_summary():
    tpl = NarrativeTemplate(id="t", body="{summary}")
    ctx = NarrationContext(branch_summary="It happened.")
    assert fill_template(tpl, ctx) == "It happened."


# --- Selection --------------------------------------------------------------


def test_select_template_filters_by_context_requirements():
    composed_tpl = NarrativeTemplate(
        id="c", body="composed body", context_requirements={"composed"}
    )
    rattled_tpl = NarrativeTemplate(
        id="r", body="rattled body", context_requirements={"rattled"}
    )
    ctx = NarrationContext(composure=0.9)  # yields tag "composed"
    pick = select_template([composed_tpl, rattled_tpl], ctx, random.Random(0))
    assert pick is composed_tpl

    ctx2 = NarrationContext(insecurity=0.8)  # yields tag "rattled"
    pick2 = select_template([composed_tpl, rattled_tpl], ctx2, random.Random(0))
    assert pick2 is rattled_tpl


def test_select_template_respects_temporal_requirements():
    arc_tpl = NarrativeTemplate(
        id="a", body="arc body", temporal_reference=TemporalRef.ARC
    )
    imm_tpl = NarrativeTemplate(
        id="i", body="imm body", temporal_reference=TemporalRef.IMMEDIATE
    )
    ctx = NarrationContext()  # no prior, no arc — both should be filtered
    assert select_template([arc_tpl, imm_tpl], ctx, random.Random(0)) is None


def test_reflective_character_favours_arc_templates():
    """A highly reflective player should sample ARC-distance templates more."""
    arc_tpl = NarrativeTemplate(
        id="a",
        body="arc body",
        temporal_reference=TemporalRef.ARC,
        base_weight=1.0,
    )
    none_tpl = NarrativeTemplate(id="n", body="now body", base_weight=1.0)

    reflective = make_player(
        reflection=_tuple(0.95, awareness=0.9, focus=0.5),
        introspection=_tuple(0.95, awareness=0.9, focus=0.5),
    )
    shallow = make_player(
        reflection=_tuple(0.05),
        introspection=_tuple(0.05),
    )

    def sample(target):
        ctx = NarrationContext(
            target=target,
            arc_summary="Something built up across weeks.",
        )
        hits = 0
        for i in range(1000):
            pick = select_template([arc_tpl, none_tpl], ctx, random.Random(i))
            if pick is arc_tpl:
                hits += 1
        return hits

    assert sample(reflective) > sample(shallow) * 1.2


def test_templates_for_event_matches_by_id_and_tags():
    id_tpl = NarrativeTemplate(id="a", body="x", event_id="training.drill_partner")
    tag_tpl = NarrativeTemplate(id="b", body="y", event_tags={"training"})
    other_tpl = NarrativeTemplate(id="c", body="z", event_tags={"conflict"})
    pool = [id_tpl, tag_tpl, other_tpl]
    out = templates_for_event(pool, "training.drill_partner", {"training"})
    assert id_tpl in out and tag_tpl in out
    assert other_tpl not in out


# --- narrate() wrapper ------------------------------------------------------


def test_narrate_falls_back_to_branch_summary_when_no_template():
    ctx = NarrationContext(branch_summary="Fallback line.")
    out = narrate([], ctx, random.Random(0))
    assert out == "Fallback line."


def test_narrate_returns_filled_template():
    player = make_player()
    tpl = NarrativeTemplate(id="t", body="{name:p} walked out.")
    ctx = NarrationContext(target=player, cast={"p": player})
    assert narrate([tpl], ctx, random.Random(0)) == "Al walked out."


# --- Arc compression --------------------------------------------------------


def test_compress_arc_summary_short_input_passes_through():
    s = "Short summary."
    assert compress_arc_summary(s, max_chars=100) == s


def test_compress_arc_summary_truncates_from_right_at_sentence_boundary():
    summary = (
        "First thing happened. Second thing happened. Third thing happened. "
        "Fourth thing happened. Fifth thing happened."
    )
    out = compress_arc_summary(summary, max_chars=60)
    assert len(out) <= 60
    # Should start at a sentence boundary (no leading space or partial word).
    assert not out.startswith(" ")
    # The most recent sentence must survive.
    assert "Fifth thing happened." in out


# --- Integration with authored content --------------------------------------


def test_authored_templates_load_and_cover_blueprints():
    content_root = Path(__file__).resolve().parents[1] / "game" / "content"
    templates = load_templates_from_path(content_root / "templates")
    blueprints = load_blueprints_from_path(content_root / "events")

    ids = {t.id for t in templates}
    assert "tpl.generic.fallback" in ids

    # Every blueprint gets at least one template (id-matched or tag-matched).
    for bp in blueprints:
        pool = templates_for_event(templates, bp.id, bp.tags)
        assert pool, f"no templates for {bp.id}"


def test_build_context_chains_arc_summary_from_log():
    from engine.outcomes import OutcomeRecord, WeekPhase

    log = [
        OutcomeRecord(
            event_id="e1",
            timestamp=WeekPhase(1, 1),
            participants={},
            branch_taken="x",
            summary="s1",
            arc_summary="chapter one",
        ),
        OutcomeRecord(
            event_id="e2",
            timestamp=WeekPhase(1, 2),
            participants={},
            branch_taken="x",
            summary="s2",
        ),
    ]
    ctx = build_narration_context(outcome_log=log)
    assert ctx.previous_outcome is log[-1]
    # Most recent arc_summary wins.
    assert ctx.arc_summary == "chapter one"


def test_narration_reads_connected_across_events_via_prior_slot():
    """Two events that share a participant and fire back-to-back produce
    narration that references the prior — this is the implicit continuity
    claim from design §7.3."""
    player = make_player()
    prior = OutcomeRecord(
        event_id="earlier",
        timestamp=WeekPhase(1, 1),
        participants={"player": "player"},
        branch_taken="x",
        summary="He had lost the ball in the warmup.",
    )
    tpl = NarrativeTemplate(
        id="follow",
        body="{prior} On the pitch, {name:player} went first to the tackle.",
        temporal_reference=TemporalRef.IMMEDIATE,
    )
    ctx = NarrationContext(
        target=player,
        cast={"player": player},
        previous_outcome=prior,
    )
    out = fill_template(tpl, ctx)
    assert "He had lost the ball in the warmup." in out
    assert "Al went first" in out
