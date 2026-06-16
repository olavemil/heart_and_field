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
    PAGE_MAX_CHARS,
    SLOT_RESOLVERS,
    TemporalRef,
    build_narration_context,
    compress_arc_summary,
    fill_template,
    narrate,
    paginate,
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
    assert out == ["Fallback line."]


def test_narrate_returns_filled_template():
    player = make_player()
    tpl = NarrativeTemplate(id="t", body="{name:p} walked out.")
    ctx = NarrationContext(target=player, cast={"p": player})
    assert narrate([tpl], ctx, random.Random(0)) == ["Al walked out."]


# --- Pagination -------------------------------------------------------------


def test_paginate_short_text_yields_single_page():
    assert paginate("One quick line.") == ["One quick line."]


def test_paginate_empty_yields_single_empty_page():
    assert paginate("") == [""]
    assert paginate("   ") == [""]


def test_paginate_splits_on_sentence_boundary_when_over_cap():
    sentences = ["Sentence number {} fills the screen.".format(i) for i in range(8)]
    text = " ".join(sentences)
    pages = paginate(text, max_chars=80)
    assert len(pages) > 1
    for page in pages:
        assert len(page) <= 80
    # Round-trip preserves content (modulo whitespace).
    assert " ".join(pages).split() == text.split()


def test_paginate_paragraph_break_forces_split():
    text = "First paragraph stays small.\n\nSecond paragraph also small."
    pages = paginate(text, max_chars=200)
    assert pages == ["First paragraph stays small.", "Second paragraph also small."]


def test_paginate_word_wraps_run_on_with_no_sentence_boundary():
    text = "word " * 60  # 300 chars of single-word tokens, no punctuation
    pages = paginate(text.strip(), max_chars=50)
    assert len(pages) > 1
    for page in pages:
        assert len(page) <= 50


def test_paginate_no_split_inside_a_word():
    text = "alpha bravo charlie delta echo foxtrot golf hotel."
    pages = paginate(text, max_chars=20)
    for page in pages:
        # Every page is whole words.
        assert all(tok in text for tok in page.split())


def test_narrate_paginates_long_template_fill_without_llm():
    player = make_player()
    long_body = (
        "{name:p} walked onto the pitch. " * 15
    ).strip()
    tpl = NarrativeTemplate(id="t", body=long_body)
    ctx = NarrationContext(target=player, cast={"p": player})
    pages = narrate([tpl], ctx, random.Random(0), max_chars=120)
    assert len(pages) > 1
    for page in pages:
        assert len(page) <= 120
        assert "Al" in page


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


def test_no_blueprint_is_generic_only():
    """Phase 22E: every blueprint has at least one non-generic template.

    Generic-only blueprints render ~⅓ of the time as the raw branch
    summary, which reads as hardcoded text in play.
    """
    content_root = Path(__file__).resolve().parents[1] / "game" / "content"
    templates = load_templates_from_path(content_root / "templates")
    blueprints = load_blueprints_from_path(content_root / "events")

    generic_only = [
        bp.id
        for bp in blueprints
        if all(
            t.id.startswith("tpl.generic")
            for t in templates_for_event(templates, bp.id, bp.tags)
        )
    ]
    assert generic_only == [], f"generic-only blueprints: {generic_only}"


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


class TestMatchPhaseNarration:
    """Phase 22F: narrated phase lines replace stat readouts."""

    def _result(self, **kwargs):
        import numpy as np

        from engine.simulation import PhaseResult

        defaults = dict(
            phase_number=1,
            performances=np.array([0.5]),
            composites=np.array([0.5]),
            team_perf=0.5,
            opp_perf=0.5,
            momentum=0.0,
            goal_scored=False,
            goal_scorer_index=None,
        )
        defaults.update(kwargs)
        return PhaseResult(**defaults)

    def test_goal_names_scorer(self):
        import random

        from engine.narrative import narrate_match_phase

        line = narrate_match_phase(
            self._result(goal_scored=True, goal_scorer_index=0),
            random.Random(1),
            scorer_name="Jordan Lee",
        )
        assert "Jordan Lee" in line
        assert "GOAL" in line

    def test_pressure_names_opponent(self):
        import random

        from engine.narrative import narrate_match_phase

        line = narrate_match_phase(
            self._result(team_perf=0.3, opp_perf=0.7),
            random.Random(1),
            opponent_name="Northgate",
        )
        assert "Northgate" in line

    def test_even_phase_returns_line(self):
        import random

        from engine.narrative import narrate_match_phase

        line = narrate_match_phase(self._result(), random.Random(1))
        assert isinstance(line, str) and len(line) > 10

    def test_late_momentum_buckets(self):
        import random

        from engine.narrative import (
            _LATE_FADE_LINES,
            _LATE_SURGE_LINES,
            narrate_match_phase,
        )

        surge = narrate_match_phase(
            self._result(momentum=0.5),
            random.Random(1),
            phase_index=7,
            total_phases=8,
            opponent_name="Northgate",
        )
        fade = narrate_match_phase(
            self._result(momentum=-0.5),
            random.Random(1),
            phase_index=7,
            total_phases=8,
            opponent_name="Northgate",
        )
        assert any(surge == l.format(opponent="Northgate") for l in _LATE_SURGE_LINES)
        assert any(fade == l.format(opponent="Northgate") for l in _LATE_FADE_LINES)

    def test_deterministic_under_seed(self):
        import random

        from engine.narrative import narrate_match_phase

        a = narrate_match_phase(self._result(), random.Random(7))
        b = narrate_match_phase(self._result(), random.Random(7))
        assert a == b


class TestSelfEvaluationLine:
    def test_bands_and_determinism(self):
        import random

        from engine.narrative import self_evaluation_line

        high = self_evaluation_line(0.9, random.Random(1))
        low = self_evaluation_line(0.1, random.Random(1))
        assert high != low
        assert self_evaluation_line(0.9, random.Random(3)) == self_evaluation_line(
            0.9, random.Random(3)
        )


class TestPronounResolvers:
    """Phase 22: pronouns track each character's gender_presentation."""

    def _ctx(self, gp):
        from engine.characters import CharacterRole, TierBCharacter
        from engine.narrative import NarrationContext

        c = TierBCharacter(id="x", name="Robin", role=CharacterRole.MIDFIELDER, stats={})
        c.gender_presentation = gp
        return NarrationContext(target=c, cast={"player": c})

    def test_masculine_feminine_androgynous(self):
        from engine.narrative import NarrativeTemplate, fill_template

        t = NarrativeTemplate(
            id="t",
            body="{name} took it. {They} said {their} piece and left {themself} nothing.",
        )
        assert fill_template(t, self._ctx("masculine")) == (
            "Robin took it. He said his piece and left himself nothing."
        )
        assert fill_template(t, self._ctx("feminine")) == (
            "Robin took it. She said her piece and left herself nothing."
        )
        assert fill_template(t, self._ctx("androgynous")) == (
            "Robin took it. They said their piece and left themself nothing."
        )

    def test_role_scoped_pronoun_uses_that_character(self):
        from engine.characters import CharacterRole, TierBCharacter
        from engine.narrative import (
            NarrationContext,
            NarrativeTemplate,
            fill_template,
        )

        player = TierBCharacter(id="p", name="Sam", role=CharacterRole.STRIKER, stats={})
        player.gender_presentation = "feminine"
        mentor = TierBCharacter(id="m", name="Lee", role=CharacterRole.MANAGER, stats={})
        mentor.gender_presentation = "masculine"
        ctx = NarrationContext(target=player, cast={"player": player, "mentor": mentor})

        t = NarrativeTemplate(
            id="t",
            body="{name:mentor} kept {their:mentor} word; {name:player} kept {theirs:player}.",
        )
        assert fill_template(t, ctx) == "Lee kept his word; Sam kept hers."

    def test_summary_slot_resolves_pronouns(self):
        """Branch summaries authored with pronoun slots resolve too."""
        from engine.narrative import NarrationContext, NarrativeTemplate, fill_template

        ctx = self._ctx("feminine")
        ctx = NarrationContext(
            target=ctx.target,
            cast=ctx.cast,
            branch_summary="{They:player} pointed a finger.",
        )
        t = NarrativeTemplate(id="t", body="{summary}")
        assert fill_template(t, ctx) == "She pointed a finger."

    def test_summary_without_slots_unchanged(self):
        from engine.narrative import NarrationContext, NarrativeTemplate, fill_template

        ctx = NarrationContext(
            target=None, cast={}, branch_summary="The room went still."
        )
        t = NarrativeTemplate(id="t", body="{summary}")
        assert fill_template(t, ctx) == "The room went still."
