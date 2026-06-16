"""Templates for mentor and rivalry events."""

from engine.narrative import NarrativeTemplate, TemporalRef


TEMPLATES = [
    # --- mentor.quiet_word --------------------------------------------------
    NarrativeTemplate(
        id="tpl.mentor.quiet.lands",
        event_id="mentor.quiet_word",
        body=(
            "{name:mentor} said it once and went back to {their:mentor} boots. The "
            "sentence stayed in {name:player}'s head on the drive home."
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.mentor.quiet.arc",
        event_id="mentor.quiet_word",
        body="{arc} Today {name:mentor}'s word went in.",
        temporal_reference=TemporalRef.ARC,
        base_weight=1.2,
    ),
    NarrativeTemplate(
        id="tpl.mentor.quiet.brushed",
        event_id="mentor.quiet_word",
        body=(
            "{name:mentor} told {them:player} the thing. {name:player} heard it and "
            "decided {they:player} already knew."
        ),
        base_weight=1.0,
        context_requirements={"confident"},
    ),
    # --- rival.challenge ----------------------------------------------------
    NarrativeTemplate(
        id="tpl.rival.challenge.meet",
        event_id="rival.challenge",
        body=(
            "{name:player} held the look. {name:rival} held it back. Neither "
            "of them moved first."
        ),
        base_weight=1.0,
        context_requirements={"confident"},
    ),
    NarrativeTemplate(
        id="tpl.rival.challenge.back",
        event_id="rival.challenge",
        body=(
            "{name:player} let it go, told {themself:player} it wasn't worth it. "
            "Later {they:player}'d know it was."
        ),
        base_weight=1.0,
        context_requirements={"rattled"},
    ),
    NarrativeTemplate(
        id="tpl.rival.challenge.arc",
        event_id="rival.challenge",
        body="{arc} {summary}",
        temporal_reference=TemporalRef.ARC,
        base_weight=1.1,
    ),
]
