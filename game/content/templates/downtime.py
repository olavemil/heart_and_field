"""Templates for downtime events — meals, travel, quiet scenes."""

from engine.narrative import NarrativeTemplate, TemporalRef


TEMPLATES = [
    NarrativeTemplate(
        id="tpl.downtime.meal.warm",
        event_id="downtime.shared_meal",
        body=(
            "{name:player} and {name:companion} ate without filling the silence. "
            "It was the kind that didn't need to be filled."
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.downtime.meal.spare",
        event_id="downtime.shared_meal",
        body="{summary}",
        base_weight=0.5,
    ),
    NarrativeTemplate(
        id="tpl.downtime.meal.rattled",
        event_id="downtime.shared_meal",
        body=(
            "{name:player} pushed food around the plate. {name:companion} didn't "
            "ask. {summary}"
        ),
        base_weight=1.1,
        context_requirements={"rattled"},
    ),
    NarrativeTemplate(
        id="tpl.downtime.travel.arc",
        event_id="downtime.travel_reading",
        body="{arc} The bus kept moving.",
        temporal_reference=TemporalRef.ARC,
        base_weight=1.2,
    ),
    NarrativeTemplate(
        id="tpl.downtime.travel.plain",
        event_id="downtime.travel_reading",
        body=(
            "{name:player} didn't turn a page for the last hour. He didn't mind."
        ),
        base_weight=1.0,
    ),
]
