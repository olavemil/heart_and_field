"""Sport-domain events not covered by existing category files."""

from engine.event_taxonomy import EventDomain, EventType, EventNature, EventTone
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
        event_id=EventType(
            nature=EventNature.COMPETITION,
            domain=EventDomain.SPORT,
            tone=EventTone.HOSTILE,
        ),
        valid_scene_types=[SceneType.TRAINING_GROUND, SceneType.PITCH],
        outcomes={
            "won": BranchOutcome(
                summary="{They:player} outran {them:rival} three times in a row. Nobody said it, but both knew.",
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
                summary="{name:rival} was quicker. Every time.",
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
        event_id=EventType(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.SPORT,
            tone=EventTone.HOSTILE,
        ),
        valid_scene_types=[SceneType.PITCH, SceneType.TRAINING_GROUND],
        outcomes={
            "stood_ground": BranchOutcome(
                summary="{They:player} took the hit and got back up. Didn't look at {name:opponent} who put {them:player} down.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.03),
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.02),
                ],
                flags={"public"},
            ),
            "snapped": BranchOutcome(
                summary="{They:player} went in high on the next challenge. The whistle came late.",
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
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="What's your response?",
            options={
                "conceded": "Trust the decision",
                "pushed_back": "Explain your view",
            },
        ))],
        base_weight=0.5,
        event_id=EventType(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.SPORT,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.TRAINING_GROUND, SceneType.LOCKER_ROOM],
        outcomes={
            "conceded": BranchOutcome(
                summary="{They:player} did what the board said. It felt wrong the whole session.",
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.03),
                ],
            ),
            "pushed_back": BranchOutcome(
                summary="{They:player} explained it once, clearly. {name:coach} stared for a long time.",
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
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you recover?",
            options={
                "processed": "Sit with it",
                "spiralled": "Run it out",
            },
        ))],
        base_weight=0.5,
        event_id=EventType(
            nature=EventNature.ISOLATION,
            domain=EventDomain.SPORT,
            tone=EventTone.MELANCHOLY,
        ),
        valid_scene_types=[SceneType.TRAINING_GROUND, SceneType.GYM],
        outcomes={
            "processed": BranchOutcome(
                summary="{They:player} stayed after everyone left. The quiet helped.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                    StatEffect("player", StatName.INTROSPECTION, 0.02),
                ],
            ),
            "spiralled": BranchOutcome(
                summary="{They:player} kept running drills alone until {their:player} legs burned. It didn't fix anything.",
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
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="What's your approach?",
            options={
                "selected": "Push for the shirt",
                "benched": "Accept the outcome",
            },
        ))],
        base_weight=0.4,
        event_id=EventType(
            nature=EventNature.NEGOTIATION,
            domain=EventDomain.SPORT,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.OFFICE, SceneType.LOCKER_ROOM],
        outcomes={
            "selected": BranchOutcome(
                summary="{They:player}'d be starting. The conversation was shorter than the worry.",
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
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you respond?",
            options={
                "faced_it": "Face the numbers",
                "dismissed": "Dismiss the data",
            },
        ))],
        base_weight=0.4,
        event_id=EventType(
            nature=EventNature.REVELATION,
            domain=EventDomain.SPORT,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.OFFICE, SceneType.LOCKER_ROOM],
        outcomes={
            "faced_it": BranchOutcome(
                summary="The numbers were clear. {They:player} looked at them longer than necessary.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                ],
            ),
            "dismissed": BranchOutcome(
                summary="{They:player} closed the screen. Data couldn't capture what the pitch felt like.",
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.03),
                ],
            ),
        },
    ),
]
