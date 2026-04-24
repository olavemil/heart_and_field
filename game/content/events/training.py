"""Training-block events (design §8.2). Low-stakes, high-frequency."""

from engine.events import (
    BranchOutcome,
    EventBlueprint,
    RelationshipEffect,
    RoleSlot,
    SceneBlock,
    StatEffect,
    WeightRule,
)
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
        blocks=[SceneBlock(id="main")],
        base_weight=1.0,
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
        blocks=[SceneBlock(id="main")],
        base_weight=0.6,
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
        blocks=[SceneBlock(id="main")],
        base_weight=0.8,
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
