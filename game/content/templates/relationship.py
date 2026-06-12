"""Templates for relationship-domain events (closeness, distance, social).

Phase 22E. Tag-attached to `social` — these wrap outcomes that range
from warm to hostile, so the framing stays observational and lets
`{summary}` carry the valence. Event_id entries cover the most frequent
relationship blueprints from playtest sims.
"""

from engine.narrative import NarrativeTemplate, TemporalRef

TEMPLATES = [
    # --- rel.cut_off ---------------------------------------------------------
    NarrativeTemplate(
        id="tpl.rel.cutoff.midword",
        event_id="rel.cut_off",
        body=(
            "{name} got half a sentence out before the shape of the "
            "conversation changed. {summary}"
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.rel.cutoff.rattled",
        event_id="rel.cut_off",
        body=(
            "{name} replayed the moment all the way home, editing it into "
            "versions where it went differently. {summary}"
        ),
        base_weight=1.1,
        context_requirements={"rattled"},
    ),
    # --- rel.boundary_talk ---------------------------------------------------
    NarrativeTemplate(
        id="tpl.rel.boundary.rehearsed",
        event_id="rel.boundary_talk",
        body=(
            "Some conversations you have once out loud and a dozen times "
            "beforehand. {summary}"
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.rel.boundary.composed",
        event_id="rel.boundary_talk",
        body=(
            "{name} kept his voice level and his hands still, and said the "
            "thing. {summary}"
        ),
        base_weight=1.1,
        context_requirements={"composed"},
    ),
    # --- tag-attached social tail --------------------------------------------
    NarrativeTemplate(
        id="tpl.rel.social.room",
        body=(
            "Rooms full of teammates have their own weather. {name} read "
            "this one on the way in. {summary}"
        ),
        event_tags={"social"},
        base_weight=0.8,
    ),
    NarrativeTemplate(
        id="tpl.rel.social.afterwards",
        body=(
            "It was the kind of moment that looks small from the outside. "
            "{summary}"
        ),
        event_tags={"social"},
        base_weight=0.8,
    ),
    NarrativeTemplate(
        id="tpl.rel.social.walkhome",
        body=(
            "{name} turned it over on the walk home, {mood_descriptor} and "
            "not quite done with it. {summary}"
        ),
        event_tags={"social"},
        base_weight=0.9,
    ),
    NarrativeTemplate(
        id="tpl.rel.social.arc",
        body=("{arc} It was still there between them. {summary}"),
        event_tags={"social"},
        base_weight=1.0,
        temporal_reference=TemporalRef.ARC,
    ),
    # --- tag-attached romantic tail -------------------------------------------
    NarrativeTemplate(
        id="tpl.rel.romantic.noticed",
        body=(
            "{name} noticed the way you notice a song you didn't mean to "
            "learn. {summary}"
        ),
        event_tags={"romantic"},
        base_weight=0.9,
    ),
    NarrativeTemplate(
        id="tpl.rel.romantic.carefully",
        body=(
            "Whatever this was, both of them were carrying it carefully. "
            "{summary}"
        ),
        event_tags={"romantic"},
        base_weight=0.9,
    ),
]
