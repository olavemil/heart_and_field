"""Templates for sport-domain events (tactics, selection, physical edge).

Phase 22E: the Phase 19 sport blueprints shipped without a pool and fell
through to the generic `{summary}` template. Tag-attached entries here
catch the training/conflict sport tail; event_id entries cover the two
highest-frequency blueprints observed in playtest sims.
"""

from engine.narrative import NarrativeTemplate

TEMPLATES = [
    # --- sport.tactical_disagreement (hottest event in sims) ----------------
    NarrativeTemplate(
        id="tpl.sport.tactics.whiteboard",
        event_id="sport.tactical_disagreement",
        body=(
            "The whiteboard had been wiped and redrawn twice already. "
            "{summary}"
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.sport.tactics.shape",
        event_id="sport.tactical_disagreement",
        body=(
            "{name} had seen the gap all week — the shape didn't cover it, "
            "whatever anyone said in the meeting. {summary}"
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.sport.tactics.confident",
        event_id="sport.tactical_disagreement",
        body=(
            "{name} said it the way you say something you've decided to "
            "stop being afraid of. {summary}"
        ),
        base_weight=1.1,
        context_requirements={"confident"},
    ),
    # --- sport.hard_tackle ---------------------------------------------------
    NarrativeTemplate(
        id="tpl.sport.tackle.sound",
        event_id="sport.hard_tackle",
        body=(
            "Everyone within twenty yards heard the contact before they saw "
            "it. {summary}"
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.sport.tackle.line",
        event_id="sport.hard_tackle",
        body=(
            "There's a line between committed and late, and the whole "
            "session ran along it. {summary}"
        ),
        base_weight=1.0,
    ),
    # --- tag-attached tail: training-flavoured ------------------------------
    NarrativeTemplate(
        id="tpl.sport.training.cones",
        body=(
            "Cones out, bibs on, the same drill until it stopped being a "
            "drill. {summary}"
        ),
        event_tags={"training"},
        base_weight=0.8,
    ),
    NarrativeTemplate(
        id="tpl.sport.training.bruised",
        body=(
            "{name} trained {mood_descriptor}, touch a half-beat off all "
            "morning. {summary}"
        ),
        event_tags={"training"},
        base_weight=1.0,
        context_requirements={"bruised"},
    ),
    NarrativeTemplate(
        id="tpl.sport.training.buoyant",
        body=(
            "Some sessions everything sticks — first touch, weight of pass, "
            "all of it. This was one. {summary}"
        ),
        event_tags={"training"},
        base_weight=1.0,
        context_requirements={"buoyant"},
    ),
    # --- tag-attached tail: status / pecking order --------------------------
    NarrativeTemplate(
        id="tpl.sport.status.order",
        body=(
            "Squads keep their own ledger of these things; nobody writes it "
            "down and nobody forgets it. {summary}"
        ),
        event_tags={"status"},
        base_weight=0.9,
    ),
]
