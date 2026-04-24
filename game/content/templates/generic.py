"""Generic templates attached by tag rather than event id.

These catch the long tail — events without bespoke template pools still
get filled narration. Tag-matched templates are weaker by default to
preserve event-specific voice where present.
"""

from engine.narrative import NarrativeTemplate, TemporalRef


TEMPLATES = [
    NarrativeTemplate(
        id="tpl.generic.fallback",
        body="{summary}",
        event_tags={
            "training",
            "downtime",
            "conflict",
            "vulnerability",
            "pregame",
            "postgame",
        },
        base_weight=0.3,
    ),
    NarrativeTemplate(
        id="tpl.generic.mood_wrap",
        body="{name} was {mood_descriptor}. {summary}",
        event_tags={"training", "downtime", "pregame"},
        base_weight=0.4,
    ),
    NarrativeTemplate(
        id="tpl.generic.arc_wrap",
        body="{arc} {summary}",
        temporal_reference=TemporalRef.ARC,
        event_tags={"conflict", "vulnerability"},
        base_weight=0.8,
    ),
]
