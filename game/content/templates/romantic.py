"""Templates for romantic events."""

from engine.narrative import NarrativeTemplate, TemporalRef


TEMPLATES = [
    NarrativeTemplate(
        id="tpl.romantic.quiet.closer",
        event_id="romantic.quiet_evening",
        body=(
            "{name:partner} didn't ask about the game. {name:player} didn't "
            "bring it up. Somewhere in the quiet, something unclenched."
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.romantic.quiet.distant",
        event_id="romantic.quiet_evening",
        body=(
            "They stayed on the edges of what mattered. When {name:player} "
            "left, neither of them said the thing they'd meant to."
        ),
        base_weight=1.0,
        context_requirements={"rattled"},
    ),
    NarrativeTemplate(
        id="tpl.romantic.arc",
        event_id="romantic.quiet_evening",
        body="{arc} Tonight it mattered less than it had.",
        temporal_reference=TemporalRef.ARC,
        base_weight=1.2,
    ),
]
