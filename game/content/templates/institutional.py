"""Templates for institutional-domain events (board, press, club machinery).

Phase 22E. The institutional voice is formal-at-a-distance: letterhead,
office doors, statements. Tone-safe across award ceremonies and
suspensions because the framing is the machinery, not the verdict.
"""

from engine.narrative import NarrativeTemplate

TEMPLATES = [
    NarrativeTemplate(
        id="tpl.inst.letterhead",
        body=(
            "Club letterhead has a way of making everything sound both "
            "official and unfinished. {summary}"
        ),
        event_tags={"institutional"},
        base_weight=0.9,
    ),
    NarrativeTemplate(
        id="tpl.inst.corridor",
        body=(
            "The corridor outside the offices was carpeted, which meant "
            "nobody heard anyone coming. {summary}"
        ),
        event_tags={"institutional"},
        base_weight=0.8,
    ),
    NarrativeTemplate(
        id="tpl.inst.business",
        body=(
            "Upstairs, the club was a business; down here it was still a "
            "team, and the two kept different books. {summary}"
        ),
        event_tags={"institutional"},
        base_weight=0.9,
    ),
    NarrativeTemplate(
        id="tpl.inst.name_said",
        body=(
            "{name} heard his own name said in the flat, careful voice "
            "people use for minutes and statements. {summary}"
        ),
        event_tags={"institutional"},
        base_weight=0.9,
    ),
    # --- external pressure (press, agents, contracts) ------------------------
    NarrativeTemplate(
        id="tpl.inst.outside_noise",
        body=(
            "The noise from outside the dressing room had a wavelength of "
            "its own that week. {summary}"
        ),
        event_tags={"external_pressure"},
        base_weight=0.9,
    ),
    NarrativeTemplate(
        id="tpl.inst.phones",
        body=(
            "It travelled the way these things travel — phone to phone, "
            "each version a little sharper than the last. {summary}"
        ),
        event_tags={"external_pressure"},
        base_weight=0.9,
    ),
]
