"""Templates for postgame events — the room after the whistle."""

from engine.narrative import NarrativeTemplate, TemporalRef


TEMPLATES = [
    NarrativeTemplate(
        id="tpl.postgame.win.shared",
        event_id="postgame.win_debrief",
        body=(
            "{name:player} let the room pull him in. For once he didn't try to "
            "hold himself apart from it."
        ),
        base_weight=1.0,
        context_requirements={"buoyant"},
    ),
    NarrativeTemplate(
        id="tpl.postgame.win.private",
        event_id="postgame.win_debrief",
        body=(
            "{name:player} packed his kit slowly. The noise of the room went on "
            "without him and he didn't mind."
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.postgame.loss.carried",
        event_id="postgame.loss_silence",
        body=(
            "No one spoke. {name:player} sat with his hands hanging between his "
            "knees and watched the floor."
        ),
        base_weight=1.1,
        context_requirements={"bruised"},
    ),
    NarrativeTemplate(
        id="tpl.postgame.loss.lashed",
        event_id="postgame.loss_silence",
        body=(
            "{name:player} hit the bench on his way past. The sound of it sat in "
            "the room longer than it should have."
        ),
        base_weight=1.0,
        context_requirements={"bruised"},
    ),
    NarrativeTemplate(
        id="tpl.postgame.loss.arc",
        event_id="postgame.loss_silence",
        body="{arc} {summary}",
        temporal_reference=TemporalRef.ARC,
        base_weight=1.2,
    ),
]
