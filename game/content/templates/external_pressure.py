"""Templates for external-pressure events — media, contracts."""

from engine.narrative import NarrativeTemplate, TemporalRef


TEMPLATES = [
    NarrativeTemplate(
        id="tpl.external.media.composed",
        event_id="external.media_scrum",
        body=(
            "{name:player} gave them the answer that had been written for {them:player}. "
            "{They:player} almost believed it on the way out."
        ),
        base_weight=1.0,
        context_requirements={"composed"},
    ),
    NarrativeTemplate(
        id="tpl.external.media.unravel",
        event_id="external.media_scrum",
        body=(
            "The question landed where it was aimed. {name:player} answered the "
            "one they'd been hoping {they:player} would."
        ),
        base_weight=1.1,
        context_requirements={"rattled"},
    ),
    NarrativeTemplate(
        id="tpl.external.contract.focused",
        event_id="external.contract_talk",
        body=(
            "The call was short. {name:player} said {they:player}'d think about it. "
            "{They:player} meant to."
        ),
        base_weight=1.0,
    ),
    NarrativeTemplate(
        id="tpl.external.contract.arc",
        event_id="external.contract_talk",
        body="{arc} The numbers hadn't been the problem.",
        temporal_reference=TemporalRef.ARC,
        base_weight=1.2,
    ),
]
