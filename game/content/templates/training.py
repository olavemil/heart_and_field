"""Narrative templates attached to training-block events.

Each event gets 4–5 variants so LLM enhancement (Phase 8) is optional.
Keep sentences short; leave room for slot resolvers to carry voice.
"""

from engine.narrative import NarrativeTemplate, TemporalRef


TEMPLATES = [
    # --- training.drill_partner (good branch) -------------------------------
    NarrativeTemplate(
        id="tpl.training.drill.good.plain",
        event_id="training.drill_partner",
        body="{summary}",
        base_weight=0.6,
    ),
    NarrativeTemplate(
        id="tpl.training.drill.good.named",
        event_id="training.drill_partner",
        body="{name:player} and {name:partner} fell into a rhythm. No words needed.",
        base_weight=1.0,
        context_requirements={"composed"},
    ),
    NarrativeTemplate(
        id="tpl.training.drill.good.warm",
        event_id="training.drill_partner",
        body=(
            "{name:player} took the ball. {name:partner} was already where it needed "
            "to go. They didn't look at each other."
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.training.drill.good.reflective",
        event_id="training.drill_partner",
        body=(
            "After the drill, {name:player} stood by the cones a moment. {prior} "
            "Something in today's run answered that."
        ),
        base_weight=0.9,
        temporal_reference=TemporalRef.IMMEDIATE,
    ),
    # --- training.coaching_moment (cross-branch pool) -----------------------
    NarrativeTemplate(
        id="tpl.training.coach.receptive.spare",
        event_id="training.coaching_moment",
        body=(
            "The coach said it once. {name:player} tried the adjustment on the next "
            "rep."
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.training.coach.receptive.arc",
        event_id="training.coaching_moment",
        body=(
            "{arc} Today the note went in without the usual flinch."
        ),
        base_weight=1.2,
        temporal_reference=TemporalRef.ARC,
    ),
    NarrativeTemplate(
        id="tpl.training.coach.defensive.terse",
        event_id="training.coaching_moment",
        body=(
            "{name:player} nodded at {name:coach}. Nothing in the next rep looked "
            "different."
        ),
        base_weight=0.9,
    ),
]
