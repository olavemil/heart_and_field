"""Templates for conflict-block events (blame, apology)."""

from engine.narrative import NarrativeTemplate, TemporalRef


TEMPLATES = [
    # --- conflict.blame_assignment ------------------------------------------
    NarrativeTemplate(
        id="tpl.conflict.blame.escalate.public",
        event_id="conflict.blame_assignment",
        body=(
            "{name:player} said {name:target}'s name the way you say it when "
            "you've been waiting. The room did not fill the silence for {them:player}."
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.conflict.blame.escalate.terse",
        event_id="conflict.blame_assignment",
        body=(
            "It came out the way {name:player} had been practising in {their:player} head. "
            "{name:target} took it standing."
        ),
        base_weight=0.9,
    ),
    NarrativeTemplate(
        id="tpl.conflict.blame.escalate.bruised",
        event_id="conflict.blame_assignment",
        body=(
            "{prior} {name:player} carried that into the room and let it land on "
            "{name:target}."
        ),
        base_weight=1.2,
        temporal_reference=TemporalRef.IMMEDIATE,
        context_requirements={"bruised"},
    ),
    NarrativeTemplate(
        id="tpl.conflict.blame.hold.rattled",
        event_id="conflict.blame_assignment",
        body=(
            "{name:player} opened {their:player} mouth and changed {their:player} mind. The word sat "
            "in the back of {their:player} throat for the rest of the evening."
        ),
        base_weight=1.0,
        context_requirements={"rattled"},
    ),
    # --- conflict.apology ---------------------------------------------------
    NarrativeTemplate(
        id="tpl.conflict.apology.sincere.arc",
        event_id="conflict.apology",
        body=(
            "{arc} {They:player} didn't soften it — said sorry, plainly, and then "
            "stopped talking."
        ),
        base_weight=1.3,
        temporal_reference=TemporalRef.ARC,
    ),
    NarrativeTemplate(
        id="tpl.conflict.apology.sincere.spare",
        event_id="conflict.apology",
        body=(
            "{name:player} found {name:target} in the corridor. The apology was "
            "short and did not look rehearsed."
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.conflict.apology.deflect",
        event_id="conflict.apology",
        body=(
            "{name:player} said the right words in the wrong order. {name:target} "
            "heard the excuses first."
        ),
        base_weight=1.0,
    ),
]
