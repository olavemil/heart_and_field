"""Downtime events (design §8.2) — shared meals, travel, waiting."""

from engine.events import (
    BranchOutcome,
    EventBlueprint,
    LocationCue,
    RelationshipEffect,
    RoleSlot,
    SceneBlock,
    StatEffect,
)
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
        blocks=[SceneBlock(id="main")],
        base_weight=0.9,
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
        outcomes={
            "reflective": BranchOutcome(
                summary="He spent the ride thinking. It settled something.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                    StatEffect("player", StatName.INTROSPECTION, 0.02),
                ],
            ),
        },
    ),
]
