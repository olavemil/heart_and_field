"""Narrative journal — temporal continuity (Phase 24A).

This is the **short-horizon** continuity track: a rolling record of the
prose the player has just read, plus compressed scene/day/week summaries.
It answers "what just happened / earlier today" and is what makes
consecutive event narrations read as one flowing scene rather than a
sequence of unconnected fragments.

It is deliberately **separate** from the arc context
(``engine.arcs`` + ``OutcomeRecord.arc_summary``), which is the
cross-time *thread* log — a quest log of storylines that ebb and flow
("last week Mara said X, you brushed her off"). The two are stored and
tracked independently and fed to the LLM as distinct, mutually-aware
grounding sections (see ``engine.llm.build_llm_prompt``):

    journal  → "Recently" / "Earlier today"   (immediate continuity)
    arc      → "Story so far"                  (long-running threads)

Conflating them is a design error: the journal compresses *time*, the
arc chain follows a *thread*. Keep the boundary strict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


# Rolling-window defaults. The recent-beat window is what the LLM sees
# verbatim for immediate continuity; once a scene closes its beats are
# compressed into a one-paragraph scene summary and dropped from the
# verbatim window so it never grows unbounded.
DEFAULT_MAX_RECENT_BEATS = 6
DEFAULT_MAX_SCENE_SUMMARIES = 8
RECENT_CONTEXT_MAX_CHARS = 600


@dataclass
class NarrativeJournal:
    """Rolling temporal-continuity record for narration grounding.

    ``recent_beats`` holds the most recent rendered narration strings
    (intro lines, outcome pages) since the current scene opened.
    ``scene_summaries`` / ``day_summaries`` / ``week_summaries`` are the
    compression layers built at the corresponding boundaries.
    """

    recent_beats: list[str] = field(default_factory=list)
    scene_summaries: list[str] = field(default_factory=list)
    day_summaries: list[str] = field(default_factory=list)
    week_summaries: list[str] = field(default_factory=list)
    max_recent_beats: int = DEFAULT_MAX_RECENT_BEATS
    max_scene_summaries: int = DEFAULT_MAX_SCENE_SUMMARIES

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_beat(self, text: str) -> None:
        """Append a rendered narration string to the rolling window.

        Empty / whitespace-only strings are ignored so blank intros and
        empty pages don't dilute the context window. The window is
        trimmed from the front to ``max_recent_beats``.
        """
        text = (text or "").strip()
        if not text:
            return
        self.recent_beats.append(text)
        if len(self.recent_beats) > self.max_recent_beats:
            self.recent_beats = self.recent_beats[-self.max_recent_beats :]

    def record_scene_summary(self, summary: str) -> None:
        """Store a closed scene's one-paragraph summary and reset the beat
        window — the verbatim beats are now folded into the summary."""
        summary = (summary or "").strip()
        if summary:
            self.scene_summaries.append(summary)
            if len(self.scene_summaries) > self.max_scene_summaries:
                self.scene_summaries = self.scene_summaries[
                    -self.max_scene_summaries :
                ]
        self.recent_beats.clear()

    def record_day_summary(self, summary: str) -> None:
        summary = (summary or "").strip()
        if summary:
            self.day_summaries.append(summary)

    def record_week_summary(self, summary: str) -> None:
        summary = (summary or "").strip()
        if summary:
            self.week_summaries.append(summary)

    # ------------------------------------------------------------------
    # Grounding
    # ------------------------------------------------------------------

    def recent_context(self, max_chars: int = RECENT_CONTEXT_MAX_CHARS) -> str | None:
        """Assemble the immediate-continuity grounding string.

        Prefers verbatim recent beats (the prose the player just read);
        when none exist yet (start of a scene) falls back to the most
        recent scene summary so the next scene still connects to the
        last. Returns ``None`` when there is nothing to ground on.

        The result is clamped to ``max_chars`` from the *end* (most
        recent text is the most load-bearing for continuity).
        """
        if self.recent_beats:
            joined = " ".join(self.recent_beats)
        elif self.scene_summaries:
            joined = self.scene_summaries[-1]
        else:
            return None
        joined = joined.strip()
        if not joined:
            return None
        if len(joined) > max_chars:
            joined = joined[-max_chars:]
            # Avoid cutting mid-word.
            space = joined.find(" ")
            if space != -1:
                joined = joined[space + 1 :]
        return joined or None

    def has_open_scene(self) -> bool:
        """True when beats have accumulated since the last scene close."""
        return bool(self.recent_beats)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "recent_beats": list(self.recent_beats),
            "scene_summaries": list(self.scene_summaries),
            "day_summaries": list(self.day_summaries),
            "week_summaries": list(self.week_summaries),
            "max_recent_beats": self.max_recent_beats,
            "max_scene_summaries": self.max_scene_summaries,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "NarrativeJournal":
        if not d:
            return cls()
        return cls(
            recent_beats=list(d.get("recent_beats", [])),
            scene_summaries=list(d.get("scene_summaries", [])),
            day_summaries=list(d.get("day_summaries", [])),
            week_summaries=list(d.get("week_summaries", [])),
            max_recent_beats=int(d.get("max_recent_beats", DEFAULT_MAX_RECENT_BEATS)),
            max_scene_summaries=int(
                d.get("max_scene_summaries", DEFAULT_MAX_SCENE_SUMMARIES)
            ),
        )
