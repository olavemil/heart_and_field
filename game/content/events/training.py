"""Training-block events (design §8.2). Low-stakes, high-frequency."""

from engine.event_taxonomy import EventDomain, EventId, EventNature, EventTone
from engine.events import (
    BranchOutcome,
    ChoiceNode,
    EventBlueprint,
    RelationshipEffect,
    RoleSlot,
    SceneBlock,
    StatEffect,
    WeightRule,
)
from engine.scene_taxonomy import SceneType
from engine.stats import StatName

from ._helpers import is_player, not_player, teammate


BLUEPRINTS = [
    EventBlueprint(
        id="training.drill_partner",
        tags={"training", "downtime"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="partner", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do the drills feel today?",
            options={
                "good": "Find the rhythm",
                "awkward": "Force the pace",
            },
        ))],
        base_weight=1.0,
        event_id=EventId(
            nature=EventNature.COLLABORATION,
            domain=EventDomain.SPORT,
            tone=EventTone.NEUTRAL,
        ),
        valid_scene_types=[SceneType.TRAINING_GROUND, SceneType.GYM, SceneType.PITCH],
        outcomes={
            "good": BranchOutcome(
                summary=(
                    "They fell into a rhythm on the drill — small adjustments, "
                    "no need to speak."
                ),
                stat_effects=[
                    StatEffect("player", StatName.FINESSE, 0.02),
                    StatEffect("partner", StatName.COLLABORATION, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="partner",
                        familiarity=0.05,
                        trust=0.03,
                    )
                ],
            ),
            "awkward": BranchOutcome(
                summary=(
                    "The rhythm never clicked. Both of them kept second-guessing "
                    "the handoff."
                ),
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="partner",
                        familiarity=0.02,
                        tension=0.02,
                    )
                ],
            ),
        },
    ),
    EventBlueprint(
        id="training.showing_off",
        tags={"training", "status"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="audience", filter=not_player, optional=True),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="Show them what you've got?",
            options={
                "landed": "Go for it",
                "missed": "Play it safe",
            },
        ))],
        base_weight=0.6,
        event_id=EventId(
            nature=EventNature.OBSERVATION,
            domain=EventDomain.SPORT,
            tone=EventTone.NEUTRAL,
        ),
        valid_scene_types=[SceneType.TRAINING_GROUND, SceneType.PITCH],
        weight_modifiers=[
            WeightRule(
                predicate=lambda ctx, st: 1.5 if ctx.momentum > 0.2 else 1.0,
                description="players show off more when riding a wave",
            )
        ],
        outcomes={
            "landed": BranchOutcome(
                summary="He pulled off the trick. The bench noticed.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.03),
                ],
                flags={"public"},
            ),
            "missed": BranchOutcome(
                summary="The trick went wide. Someone laughed.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, -0.03),
                    StatEffect("player", StatName.INSECURITY, 0.03),
                ],
                flags={"public"},
            ),
        },
    ),
    EventBlueprint(
        id="training.coaching_moment",
        tags={"training", "mentor"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(
                role="coach",
                filter=lambda c: c.role.value in {"manager", "assistant_coach"},
            ),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you take the feedback?",
            options={
                "receptive": "Learn from it",
                "defensive": "Brush it off",
            },
        ))],
        base_weight=0.8,
        event_id=EventId(
            nature=EventNature.COLLABORATION,
            domain=EventDomain.SPORT,
            tone=EventTone.WARM,
        ),
        valid_scene_types=[SceneType.TRAINING_GROUND, SceneType.PITCH],
        outcomes={
            "receptive": BranchOutcome(
                summary="The note landed. He tried the adjustment immediately.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.02),
                    StatEffect("player", StatName.FINESSE, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="coach",
                        familiarity=0.03,
                        trust=0.04,
                    )
                ],
            ),
            "defensive": BranchOutcome(
                summary=(
                    "He nodded, but the adjustment didn't happen. Something in "
                    "him pushed back."
                ),
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.03),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="coach",
                        tension=0.04,
                    )
                ],
            ),
        },
    ),
]
