"""Templates for secret-domain events (concealment, discovery, leverage).

Phase 22E. The secret voice is about weight and surface — what's
carried, what shows, what almost shows. Tone-safe whether the secret is
the player's or someone else's, kept or cracked open; `{summary}`
carries the specifics.
"""

from engine.narrative import NarrativeTemplate, TemporalRef

TEMPLATES = [
    NarrativeTemplate(
        id="tpl.secret.weight",
        body=(
            "Some things you carry in a bag; some things you carry in your "
            "posture. {summary}"
        ),
        event_tags={"secret"},
        base_weight=0.9,
    ),
    NarrativeTemplate(
        id="tpl.secret.surface",
        body=(
            "It was almost visible, the way deep water is almost a colour. "
            "{summary}"
        ),
        event_tags={"secret"},
        base_weight=0.9,
    ),
    NarrativeTemplate(
        id="tpl.secret.doors",
        body=(
            "{name} had learned which conversations to leave by which "
            "doors. {summary}"
        ),
        event_tags={"secret"},
        base_weight=0.9,
    ),
    NarrativeTemplate(
        id="tpl.secret.rattled",
        body=(
            "{name} counted who'd been in the room, twice, and didn't like "
            "the arithmetic either time. {summary}"
        ),
        event_tags={"secret"},
        base_weight=1.1,
        context_requirements={"rattled"},
    ),
    NarrativeTemplate(
        id="tpl.secret.arc",
        body=(
            "{arc} The thing underneath it hadn't moved. {summary}"
        ),
        event_tags={"secret"},
        base_weight=1.0,
        temporal_reference=TemporalRef.ARC,
    ),
]
