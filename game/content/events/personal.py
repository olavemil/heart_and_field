"""Personal-domain events — private moments of growth or difficulty."""

from engine.event_taxonomy import EventDomain, EventId, EventNature, EventTone
from engine.events import (
    BranchOutcome,
    ChoiceNode,
    EventBlueprint,
    RoleSlot,
    SceneBlock,
    StatEffect,
)
from engine.scene_taxonomy import SceneType
from engine.stats import StatName

from ._helpers import is_player, not_player


BLUEPRINTS = [
    # --- personal.celebration.warm ---
    EventBlueprint(
        id="personal.quiet_pride",
        tags={"downtime", "solo"},
        participants=[RoleSlot(role="player", filter=is_player)],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="What do you do with the feeling?",
            options={
                "sat_with_it": "Sit with it",
                "deflected": "Move past it",
            },
        ))],
        base_weight=0.4,
        event_id=EventId(
            nature=EventNature.CELEBRATION,
            domain=EventDomain.PERSONAL,
            tone=EventTone.WARM,
        ),
        valid_scene_types=[SceneType.APARTMENT, SceneType.HOUSE],
        outcomes={
            "sat_with_it": BranchOutcome(
                summary="He didn't tell anyone. He let himself feel it alone for a moment.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.02),
                    StatEffect("player", StatName.REFLECTION, 0.02),
                ],
            ),
            "deflected": BranchOutcome(
                summary="It passed before he could name it. He moved on to the next thing.",
                stat_effects=[
                    StatEffect("player", StatName.CAUTIOUSNESS, 0.02),
                ],
            ),
        },
    ),
    # --- personal.consolation.warm ---
    EventBlueprint(
        id="personal.kind_stranger",
        tags={"downtime", "social"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="stranger", filter=not_player, optional=True),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you take it?",
            options={
                "received": "Let it in",
                "brushed_off": "Brush it off",
            },
        ))],
        base_weight=0.3,
        event_id=EventId(
            nature=EventNature.CONSOLATION,
            domain=EventDomain.PERSONAL,
            tone=EventTone.WARM,
        ),
        valid_scene_types=[SceneType.CAFE, SceneType.PARK],
        outcomes={
            "received": BranchOutcome(
                summary="Someone said the right thing at the right time. He didn't know their name.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, -0.02),
                    StatEffect("player", StatName.MOTIVATION, 0.02),
                ],
            ),
            "brushed_off": BranchOutcome(
                summary="The kindness bounced off. He wasn't ready for it.",
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.02),
                ],
            ),
        },
    ),
]
