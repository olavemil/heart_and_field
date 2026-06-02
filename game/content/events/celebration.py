"""Celebration events (design §8.2) — moments where joy gets expressed."""

from engine.event_taxonomy import EventDomain, EventId, EventNature, EventTone
from engine.events import (
    BranchOutcome,
    EventBlueprint,
    RelationshipEffect,
    RoleSlot,
    SceneBlock,
    StatEffect,
    WeightRule,
)
from engine.scene_taxonomy import SceneType
from engine.stats import StatName

from ._helpers import is_player, teammate


BLUEPRINTS = [
    EventBlueprint(
        id="celebration.goal_huddle",
        tags={"celebration", "ingame"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="scorer", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.7,
        event_id=EventId(
            nature=EventNature.CELEBRATION,
            domain=EventDomain.SPORT,
            tone=EventTone.TRIUMPHANT,
        ),
        valid_scene_types=[SceneType.PITCH],
        weight_modifiers=[
            WeightRule(
                predicate=lambda ctx, st: 1.8 if ctx.momentum > 0.3 else 0.6,
                description="more likely when riding momentum",
            )
        ],
        outcomes={
            "warm": BranchOutcome(
                summary=(
                    "He got to {name:scorer} first. The hug was brief and "
                    "honest."
                ),
                stat_effects=[
                    StatEffect("player", StatName.MOTIVATION, 0.03),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="scorer",
                        familiarity=0.04,
                        trust=0.03,
                    )
                ],
            ),
            "held_back": BranchOutcome(
                summary=(
                    "He ran to the edge of the huddle and stopped there. Something "
                    "kept him from the middle of it."
                ),
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
            ),
        },
    ),
]
