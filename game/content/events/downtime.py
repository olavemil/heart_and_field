"""Downtime events (design §8.2) — shared meals, travel, waiting."""

from engine.event_taxonomy import EventDomain, EventType, EventNature, EventTone
from engine.events import (
    BranchOutcome,
    ChoiceNode,
    EventBlueprint,
    LocationCue,
    PlayerStance,
    RelationshipEffect,
    RoleSlot,
    SceneBlock,
    StatEffect,
)
from engine.scene_taxonomy import SceneType
from engine.secrets import AspectType
from engine.stats import StatName

from ._helpers import is_player, teammate


BLUEPRINTS = [
    EventBlueprint(
        id="downtime.shared_meal",
        tags={"downtime", "social"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="companion", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How's the meal?",
            options={
                "easy": "Enjoy the company",
                "silent": "Sit quietly",
            },
        ))],
        base_weight=0.9,
        event_id=EventType(
            nature=EventNature.INVITATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.WARM,
        ),
        valid_scene_types=[
            SceneType.RESTAURANT, SceneType.CAFE, SceneType.HOUSE,
        ],
        boosted_by_aspects=[AspectType.RELATIONSHIP],
        location=LocationCue(
            spec_id="suburban_house",
            node_name="kitchen",
            graph_id="player_home",
        ),
        outcomes={
            "easy": BranchOutcome(
                summary=(
                    "They talked about nothing in particular, and it was enough."
                ),
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="companion",
                        familiarity=0.06,
                        trust=0.02,
                    )
                ],
                stat_effects=[
                    StatEffect("player", StatName.COLLABORATION, 0.01),
                ],
            ),
            "silent": BranchOutcome(
                summary="Neither of them felt like speaking. The meal passed.",
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="companion",
                        familiarity=0.02,
                    )
                ],
            ),
        },
    ),
    EventBlueprint(
        id="downtime.travel_reading",
        tags={"downtime", "solo"},
        participants=[RoleSlot(role="player", filter=is_player)],
        blocks=[SceneBlock(id="main")],
        base_weight=0.5,
        # Withdrawn from the team around them, in their own world.
        player_stance=PlayerStance.ONLOOKER,
        event_id=EventType(
            nature=EventNature.ISOLATION,
            domain=EventDomain.PERSONAL,
            tone=EventTone.MELANCHOLY,
        ),
        valid_scene_types=[SceneType.BUS, SceneType.PLANE, SceneType.CAR],
        outcomes={
            "reflective": BranchOutcome(
                summary="{They:player} spent the ride thinking. It settled something.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                    StatEffect("player", StatName.INTROSPECTION, 0.02),
                ],
            ),
        },
    ),
]
