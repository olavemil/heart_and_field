"""Templates for celebration events."""

from engine.narrative import NarrativeTemplate


TEMPLATES = [
    NarrativeTemplate(
        id="tpl.celebration.huddle.warm",
        event_id="celebration.goal_huddle",
        body=(
            "{name:player} got to {name:scorer} first. The hug was brief and "
            "honest and then the game started again."
        ),
        base_weight=1.0,
        context_requirements={"buoyant"},
    ),
    NarrativeTemplate(
        id="tpl.celebration.huddle.plain",
        event_id="celebration.goal_huddle",
        body="{summary}",
        base_weight=0.7,
    ),
    NarrativeTemplate(
        id="tpl.celebration.huddle.edge",
        event_id="celebration.goal_huddle",
        body=(
            "{name:player} reached the edge of the huddle and stopped. {They:player} "
            "clapped twice, then jogged back to {their:player} position."
        ),
        base_weight=1.0,
        context_requirements={"rattled"},
    ),
]
