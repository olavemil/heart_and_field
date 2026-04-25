"""Templates for pregame events — rituals, the locker room, nerves."""

from engine.narrative import NarrativeTemplate, TemporalRef


TEMPLATES = [
    NarrativeTemplate(
        id="tpl.pregame.speech.rousing",
        event_id="pregame.locker_room_speech",
        body=(
            "{name:speaker} found the words for it. {name:player} felt the room "
            "steady under them."
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.pregame.speech.flat",
        event_id="pregame.locker_room_speech",
        body=(
            "{name:speaker} said something. {name:player} couldn't have told "
            "you what."
        ),
        base_weight=1.0,
        context_requirements={"rattled"},
    ),
    NarrativeTemplate(
        id="tpl.pregame.speech.arc",
        event_id="pregame.locker_room_speech",
        body="{arc} Today the speech had to do the work.",
        temporal_reference=TemporalRef.ARC,
        base_weight=1.1,
    ),
    NarrativeTemplate(
        id="tpl.pregame.ritual.centred",
        event_id="pregame.ritual",
        body=(
            "{name:player} went through it the way he always did. Laces, "
            "breathing, the tap against the crossbar. The quiet worked."
        ),
        base_weight=1.0,
        context_requirements={"composed"},
    ),
    NarrativeTemplate(
        id="tpl.pregame.ritual.hollow",
        event_id="pregame.ritual",
        body=(
            "The ritual didn't take. {name:player} stood for a moment with his "
            "hand on the wall and waited for something to arrive."
        ),
        base_weight=1.0,
        context_requirements={"rattled"},
    ),
]
