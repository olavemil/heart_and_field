"""Templates for solo / interior events (quiet pride, private doubt).

Phase 22E. Tag-attached to `solo` — events with no other cast, so the
camera stays inside the player's head. Mood-gated variants split the
valence without presuming what the outcome was.
"""

from engine.narrative import NarrativeTemplate

TEMPLATES = [
    NarrativeTemplate(
        id="tpl.solo.unwitnessed",
        body=(
            "Nobody saw it, which was somehow the point. {summary}"
        ),
        event_tags={"solo"},
        base_weight=0.9,
    ),
    NarrativeTemplate(
        id="tpl.solo.interior",
        body=(
            "{name} kept his own counsel about it, the way he kept it about "
            "most things that mattered. {summary}"
        ),
        event_tags={"solo"},
        base_weight=0.9,
    ),
    NarrativeTemplate(
        id="tpl.solo.buoyant",
        body=(
            "There was a lightness to the evening {name} didn't bother to "
            "explain to anyone. {summary}"
        ),
        event_tags={"solo"},
        base_weight=1.0,
        context_requirements={"buoyant"},
    ),
    NarrativeTemplate(
        id="tpl.solo.bruised",
        body=(
            "Alone was easier; alone didn't ask follow-up questions. "
            "{summary}"
        ),
        event_tags={"solo"},
        base_weight=1.0,
        context_requirements={"bruised"},
    ),
    NarrativeTemplate(
        id="tpl.solo.smallhours",
        body=(
            "It surfaced in the small hours, the way these things do, and "
            "{name} let it sit with him a while. {summary}"
        ),
        event_tags={"solo"},
        base_weight=0.8,
    ),
]
