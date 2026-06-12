"""Sport-domain events not covered by existing category files."""

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
    # --- sport.competition.hostile ---
    EventBlueprint(
        id="sport.position_battle",
        tags={"training", "conflict"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="rival", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you answer the challenge?",
            options={
                "won": "Push harder still",
                "lost": "Accept the lesson",
            },
        ))],
        base_weight=0.5,
        event_id=EventId(
            nature=EventNature.COMPETITION,
            domain=EventDomain.SPORT,
            tone=EventTone.HOSTILE,
        ),
        valid_scene_types=[SceneType.TRAINING_GROUND, SceneType.PITCH],
        outcomes={
            "won": BranchOutcome(
                summary="He outran him three times in a row. Nobody said it, but they both knew.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.04),
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="rival",
                        tension=0.08, familiarity=0.03,
                    ),
                ],
            ),
            "lost": BranchOutcome(
                summary="The other man was quicker. Every time.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.04),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="rival",
                        tension=0.05,
                    ),
                ],
            ),
        },
    ),
    # --- sport.confrontation.hostile ---
    EventBlueprint(
        id="sport.hard_tackle",
        tags={"training", "conflict"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="opponent", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="Do you retaliate?",
            options={
                "stood_ground": "Keep your composure",
                "snapped": "Go in harder",
            },
        ))],
        base_weight=0.4,
        event_id=EventId(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.SPORT,
            tone=EventTone.HOSTILE,
        ),
        valid_scene_types=[SceneType.PITCH, SceneType.TRAINING_GROUND],
        outcomes={
            "stood_ground": BranchOutcome(
                summary="He took the hit and got back up. Didn't look at the man who put him down.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.03),
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.02),
                ],
                flags={"public"},
            ),
            "snapped": BranchOutcome(
                summary="He went in high on the next challenge. The whistle came late.",
                stat_effects=[
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.05),
                    StatEffect("player", StatName.CAUTIOUSNESS, -0.03),
                ],
                flags={"public", "unresolved"},
            ),
        },
    ),
    # --- sport.confrontation.tense ---
    EventBlueprint(
        id="sport.tactical_disagreement",
        tags={"training", "conflict"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="coach",
                     filter=lambda c: c.role.value in {"manager", "assistant_coach"}),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.5,
        event_id=EventId(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.SPORT,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.TRAINING_GROUND, SceneType.LOCKER_ROOM],
        outcomes={
            "conceded": BranchOutcome(
                summary="He did what the board said. It felt wrong the whole session.",
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.03),
                ],
            ),
            "pushed_back": BranchOutcome(
                summary="He explained it once, clearly. The coach stared for a long time.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.02),
                    StatEffect("player", StatName.LEADERSHIP, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="coach",
                        tension=0.06, familiarity=0.02,
                    ),
                ],
            ),
        },
    ),
    # --- sport.isolation.melancholy ---
    EventBlueprint(
        id="sport.solo_warmdown",
        tags={"training", "solo"},
        participants=[RoleSlot(role="player", filter=is_player)],
        blocks=[SceneBlock(id="main")],
        base_weight=0.5,
        event_id=EventId(
            nature=EventNature.ISOLATION,
            domain=EventDomain.SPORT,
            tone=EventTone.MELANCHOLY,
        ),
        valid_scene_types=[SceneType.TRAINING_GROUND, SceneType.GYM],
        outcomes={
            "processed": BranchOutcome(
                summary="He stayed after everyone left. The quiet helped.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                    StatEffect("player", StatName.INTROSPECTION, 0.02),
                ],
            ),
            "spiralled": BranchOutcome(
                summary="He kept running drills alone until his legs burned. It didn't fix anything.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.03),
                    StatEffect("player", StatName.STAMINA, 0.01),
                ],
            ),
        },
    ),
    # --- sport.negotiation.tense ---
    EventBlueprint(
        id="sport.selection_talk",
        tags={"pregame", "institutional"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="coach",
                     filter=lambda c: c.role.value in {"manager", "assistant_coach"}),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.4,
        event_id=EventId(
            nature=EventNature.NEGOTIATION,
            domain=EventDomain.SPORT,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.OFFICE, SceneType.LOCKER_ROOM],
        outcomes={
            "selected": BranchOutcome(
                summary="He'd be starting. The conversation was shorter than the worry.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.03),
                    StatEffect("player", StatName.MOTIVATION, 0.02),
                ],
            ),
            "benched": BranchOutcome(
                summary="The coach said 'next week' in a tone that didn't promise anything.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.04),
                    StatEffect("player", StatName.MOTIVATION, -0.03),
                ],
            ),
        },
    ),
    # --- sport.revelation.tense ---
    EventBlueprint(
        id="sport.performance_data",
        tags={"training", "institutional"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="analyst", filter=not_player, optional=True),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.4,
        event_id=EventId(
            nature=EventNature.REVELATION,
            domain=EventDomain.SPORT,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.OFFICE, SceneType.LOCKER_ROOM],
        outcomes={
            "faced_it": BranchOutcome(
                summary="The numbers were clear. He looked at them longer than he needed to.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                ],
            ),
            "dismissed": BranchOutcome(
                summary="He closed the screen. Data couldn't tell you what the pitch felt like.",
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.03),
                ],
            ),
        },
    ),
]
