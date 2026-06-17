"""Tests for engine.journal — temporal-continuity track (Phase 24A).

The journal is deliberately separate from the arc context: it tracks
recently rendered prose + scene/day/week summaries (immediate flow),
not long-running threads (the arc digest chain). These tests cover the
rolling window, compression hand-off, grounding string, and round-trip.
"""

from __future__ import annotations

from engine.journal import (
    DEFAULT_MAX_RECENT_BEATS,
    NarrativeJournal,
)


class TestRecordBeat:
    def test_records_and_trims_to_window(self):
        j = NarrativeJournal(max_recent_beats=3)
        for i in range(5):
            j.record_beat(f"beat {i}")
        assert j.recent_beats == ["beat 2", "beat 3", "beat 4"]

    def test_ignores_blank_beats(self):
        j = NarrativeJournal()
        j.record_beat("")
        j.record_beat("   ")
        j.record_beat(None)  # type: ignore[arg-type]
        assert j.recent_beats == []

    def test_strips_whitespace(self):
        j = NarrativeJournal()
        j.record_beat("  hello  ")
        assert j.recent_beats == ["hello"]


class TestSceneSummary:
    def test_summary_resets_verbatim_window(self):
        j = NarrativeJournal()
        j.record_beat("a")
        j.record_beat("b")
        assert j.has_open_scene()
        j.record_scene_summary("They talked. It went poorly.")
        assert not j.has_open_scene()
        assert j.recent_beats == []
        assert j.scene_summaries == ["They talked. It went poorly."]

    def test_blank_summary_still_resets_window(self):
        # A scene with nothing worth summarising should still clear beats
        # so they don't leak into the next scene.
        j = NarrativeJournal()
        j.record_beat("a")
        j.record_scene_summary("")
        assert j.recent_beats == []
        assert j.scene_summaries == []

    def test_scene_summaries_trim_to_cap(self):
        j = NarrativeJournal(max_scene_summaries=2)
        for i in range(4):
            j.record_beat("x")
            j.record_scene_summary(f"summary {i}")
        assert j.scene_summaries == ["summary 2", "summary 3"]


class TestRecentContext:
    def test_none_when_empty(self):
        assert NarrativeJournal().recent_context() is None

    def test_prefers_verbatim_beats(self):
        j = NarrativeJournal()
        j.record_scene_summary("old scene")  # populates scene_summaries
        j.record_beat("fresh prose")
        assert j.recent_context() == "fresh prose"

    def test_falls_back_to_last_scene_summary(self):
        j = NarrativeJournal()
        j.record_beat("x")
        j.record_scene_summary("the scene summary")
        # window cleared → grounding uses the summary
        assert j.recent_context() == "the scene summary"

    def test_clamps_to_max_chars_without_splitting_word(self):
        j = NarrativeJournal()
        j.record_beat("alpha bravo charlie delta echo foxtrot golf hotel")
        out = j.recent_context(max_chars=20)
        assert out is not None
        assert len(out) <= 20
        # Clamp slices from the end; should not start mid-word.
        assert not out.startswith(" ")
        assert "hotel" in out


class TestSerialisation:
    def test_round_trip(self):
        j = NarrativeJournal(max_recent_beats=4)
        j.record_beat("b1")
        j.record_beat("b2")
        j.record_scene_summary("scene one")
        j.record_beat("b3")
        j.record_day_summary("day one")
        j.record_week_summary("week one")

        restored = NarrativeJournal.from_dict(j.to_dict())
        assert restored.recent_beats == j.recent_beats
        assert restored.scene_summaries == j.scene_summaries
        assert restored.day_summaries == j.day_summaries
        assert restored.week_summaries == j.week_summaries
        assert restored.max_recent_beats == 4

    def test_from_empty_dict(self):
        j = NarrativeJournal.from_dict(None)
        assert j.recent_beats == []
        assert j.max_recent_beats == DEFAULT_MAX_RECENT_BEATS

    def test_from_partial_dict(self):
        j = NarrativeJournal.from_dict({"recent_beats": ["only"]})
        assert j.recent_beats == ["only"]
        assert j.scene_summaries == []
