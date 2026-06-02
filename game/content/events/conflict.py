"""Conflict events — blame, jealousy, competition (design §8.2).

Includes a simple arc (blame → apology) to exercise prereqs and
`carries_arc_context` in Phase 3's tests.
"""

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
from engine.secrets import AspectType
from engine.stats import StatName

from ._helpers import is_player, not_player, teammate


BLUEPRINTS = [
    EventBlueprint(
        id="conflict.blame_assignment",
        tags={"conflict", "postgame"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="target", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.4,
        event_id=EventId(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.HOSTILE,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.TRAINING_GROUND],
        boosted_by_aspects=[AspectType.HISTORY],
        reveals_exposure=0.1,
        weight_modifiers=[
            WeightRule(
                predicate=lambda ctx, st: 2.0 if ctx.team_morale < -0.2 else 1.0,
                description="blame flares after a loss",
            )
        ],
        carries_arc_context=True,
        unlocks=["conflict.apology"],
        outcomes={
            "escalate": BranchOutcome(
                summary=(
                    "He pointed a finger. The room went still; the accusation "
                    "landed wide of anyone who could deflect it."
                ),
                stat_effects=[
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.03),
                    StatEffect("target", StatName.DEFENSIVENESS, 0.04),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="target",
                        tension=0.15,
                        trust=-0.08,
                    )
                ],
                flags={"unresolved", "public"},
            ),
            "hold_back": BranchOutcome(
                summary="He swallowed it. Said nothing. Something sat wrong.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.02),
                    StatEffect("player", StatName.REFLECTION, 0.02),
                ],
            ),
        },
    ),
    EventBlueprint(
        id="conflict.apology",
        tags={"conflict", "resolution"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="target", filter=not_player),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.7,
        event_id=EventId(
            nature=EventNature.ADMISSION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.MELANCHOLY,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.PARK],
        prerequisites=["conflict.blame_assignment"],
        carries_arc_context=True,
        outcomes={
            "sincere": BranchOutcome(
                summary=(
                    "He said it plainly. No qualifiers. The other man looked "
                    "at the floor for a long time before answering."
                ),
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                    StatEffect("target", StatName.DEFENSIVENESS, -0.03),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="target",
                        trust=0.12,
                        tension=-0.15,
                    )
                ],
            ),
            "deflect": BranchOutcome(
                summary=(
                    "The apology came wrapped in excuses. It read as another "
                    "kind of blame."
                ),
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.04),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="target",
                        tension=0.05,
                    )
                ],
                flags={"unresolved"},
            ),
        },
    ),
]
