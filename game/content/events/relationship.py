"""Relationship-domain events not covered by existing category files."""

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
from engine.secrets import AspectType
from engine.stats import StatName

from ._helpers import is_player, not_player, teammate


BLUEPRINTS = [
    # --- relationship.admission.romantic ---
    EventBlueprint(
        id="rel.romantic_admission",
        tags={"romantic", "vulnerability"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="interest", filter=not_player),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="Do you say it?",
            options={
                "said_it": "Say what you feel",
                "held_back": "Keep it to yourself",
            },
        ))],
        base_weight=0.3,
        event_id=EventId(
            nature=EventNature.ADMISSION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.ROMANTIC,
        ),
        valid_scene_types=[SceneType.PARK, SceneType.CAFE, SceneType.APARTMENT],
        boosted_by_aspects=[AspectType.RELATIONSHIP],
        outcomes={
            "said_it": BranchOutcome(
                summary="He said what he'd been thinking. The silence after was longer than the sentence.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, -0.02),
                    StatEffect("player", StatName.CONFIDENCE, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="interest",
                        attraction=0.08, familiarity=0.05, trust=0.04,
                    ),
                ],
            ),
            "held_back": BranchOutcome(
                summary="He almost said it. The moment passed and he let it.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.03),
                ],
            ),
        },
    ),
    # --- relationship.celebration.playful ---
    EventBlueprint(
        id="rel.team_night_out",
        tags={"social", "celebration"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="mate", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you settle in?",
            options={
                "loosened_up": "Join the moment",
                "awkward": "Stay on the edge",
            },
        ))],
        base_weight=0.5,
        event_id=EventId(
            nature=EventNature.CELEBRATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.PLAYFUL,
        ),
        valid_scene_types=[SceneType.BAR, SceneType.CLUB, SceneType.RESTAURANT],
        outcomes={
            "loosened_up": BranchOutcome(
                summary="For a few hours nobody talked about football. It was the best night in weeks.",
                stat_effects=[
                    StatEffect("player", StatName.MOTIVATION, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="mate",
                        familiarity=0.06, trust=0.03,
                    ),
                ],
            ),
            "awkward": BranchOutcome(
                summary="He sat at the edge of the table and left before anyone noticed.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
            ),
        },
    ),
    # --- relationship.celebration.warm ---
    EventBlueprint(
        id="rel.small_victory",
        tags={"social", "celebration"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="companion", filter=not_player),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you share the moment?",
            options={
                "shared": "Tell them everything",
                "understated": "Let them notice it",
            },
        ))],
        base_weight=0.5,
        event_id=EventId(
            nature=EventNature.CELEBRATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.WARM,
        ),
        valid_scene_types=[SceneType.CAFE, SceneType.HOUSE, SceneType.RESTAURANT],
        outcomes={
            "shared": BranchOutcome(
                summary="He told them about it. Their reaction made it feel real.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="companion",
                        familiarity=0.04, trust=0.03,
                    ),
                ],
            ),
            "understated": BranchOutcome(
                summary="He mentioned it in passing. They noticed anyway.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.02),
                ],
            ),
        },
    ),
    # --- relationship.collaboration.warm ---
    EventBlueprint(
        id="rel.joint_effort",
        tags={"social", "downtime"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="partner", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How does the work unfold?",
            options={
                "clicked": "Let conversation flow",
                "strained": "Stay focused on the task",
            },
        ))],
        base_weight=0.6,
        event_id=EventId(
            nature=EventNature.COLLABORATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.WARM,
        ),
        valid_scene_types=[SceneType.HOUSE, SceneType.CAFE],
        outcomes={
            "clicked": BranchOutcome(
                summary="They finished each other's thoughts. The thing they built wasn't the point.",
                stat_effects=[
                    StatEffect("player", StatName.COLLABORATION, 0.03),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="partner",
                        familiarity=0.05, trust=0.04,
                    ),
                ],
            ),
            "strained": BranchOutcome(
                summary="They got it done, but the conversation felt like negotiation.",
                stat_effects=[
                    StatEffect("player", StatName.CAUTIOUSNESS, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="partner",
                        tension=0.03,
                    ),
                ],
            ),
        },
    ),
    # --- relationship.confrontation.tense ---
    EventBlueprint(
        id="rel.unspoken_grudge",
        tags={"conflict", "social"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="other", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="What do you do?",
            options={
                "surfaced": "Name what's between you",
                "swallowed": "Let it go unsaid",
            },
        ))],
        base_weight=0.4,
        event_id=EventId(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.CAFE],
        outcomes={
            "surfaced": BranchOutcome(
                summary="Neither raised their voice. That made it worse.",
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.03),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="other",
                        tension=0.10, familiarity=0.03,
                    ),
                ],
            ),
            "swallowed": BranchOutcome(
                summary="He let it pass. The conversation moved on but nothing was settled.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
            ),
        },
    ),
    # --- relationship.consolation.melancholy ---
    EventBlueprint(
        id="rel.late_night_talk",
        tags={"vulnerability", "social"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="friend", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="Can you reach them?",
            options={
                "helped": "Sit with them in it",
                "empty": "Try to fix what's broken",
            },
        ))],
        base_weight=0.4,
        event_id=EventId(
            nature=EventNature.CONSOLATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.MELANCHOLY,
        ),
        valid_scene_types=[SceneType.APARTMENT, SceneType.HOUSE],
        outcomes={
            "helped": BranchOutcome(
                summary="They sat with it together. Neither of them fixed anything.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.02),
                    StatEffect("player", StatName.INSECURITY, -0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="friend",
                        trust=0.06, familiarity=0.04,
                    ),
                ],
            ),
            "empty": BranchOutcome(
                summary="The words were kind. They didn't reach.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
            ),
        },
    ),
    # --- relationship.consolation.warm ---
    EventBlueprint(
        id="rel.reassurance",
        tags={"social", "vulnerability"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="supporter", filter=not_player),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="Do you accept their reassurance?",
            options={
                "landed": "Let it in",
                "resisted": "Stay in doubt",
            },
        ))],
        base_weight=0.5,
        event_id=EventId(
            nature=EventNature.CONSOLATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.WARM,
        ),
        valid_scene_types=[SceneType.CAFE, SceneType.HOUSE, SceneType.PARK],
        outcomes={
            "landed": BranchOutcome(
                summary="The reassurance came without being asked. He let it in.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.02),
                    StatEffect("player", StatName.INSECURITY, -0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="supporter",
                        trust=0.05, familiarity=0.03,
                    ),
                ],
            ),
            "resisted": BranchOutcome(
                summary="He said he was fine. They both knew he wasn't.",
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.02),
                ],
            ),
        },
    ),
    # --- relationship.isolation.melancholy ---
    EventBlueprint(
        id="rel.left_out",
        tags={"social", "vulnerability"},
        participants=[RoleSlot(role="player", filter=is_player)],
        blocks=[SceneBlock(id="main")],
        base_weight=0.4,
        event_id=EventId(
            nature=EventNature.ISOLATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.MELANCHOLY,
        ),
        valid_scene_types=[SceneType.APARTMENT, SceneType.HOUSE],
        outcomes={
            "accepted": BranchOutcome(
                summary="They went without him. He noticed the silence in the flat.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.02),
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
            ),
            "bitter": BranchOutcome(
                summary="He told himself he didn't want to go anyway.",
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.03),
                ],
            ),
        },
    ),
    # --- relationship.negotiation.tense ---
    EventBlueprint(
        id="rel.boundary_talk",
        tags={"social", "conflict"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="other", filter=not_player),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.4,
        event_id=EventId(
            nature=EventNature.NEGOTIATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.CAFE, SceneType.APARTMENT],
        outcomes={
            "agreed": BranchOutcome(
                summary="They found a line. Neither liked where it landed.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="other",
                        trust=0.03, tension=-0.04,
                    ),
                ],
            ),
            "stalemated": BranchOutcome(
                summary="Neither moved. They left the conversation exactly where they found it.",
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="other",
                        tension=0.05,
                    ),
                ],
            ),
        },
    ),
    # --- relationship.observation.neutral ---
    EventBlueprint(
        id="rel.watching_others",
        tags={"social", "downtime"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="subject", filter=teammate(), optional=True),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.5,
        event_id=EventId(
            nature=EventNature.OBSERVATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.NEUTRAL,
        ),
        valid_scene_types=[SceneType.CAFE, SceneType.PARK, SceneType.LOCKER_ROOM],
        reveals_exposure=0.05,
        outcomes={
            "noticed": BranchOutcome(
                summary="He saw something in how they moved around each other. It stayed with him.",
                stat_effects=[
                    StatEffect("player", StatName.INTROSPECTION, 0.02),
                ],
            ),
            "missed": BranchOutcome(
                summary="He was there but his mind was somewhere else.",
                stat_effects=[],
            ),
        },
    ),
    # --- relationship.rejection.hostile ---
    EventBlueprint(
        id="rel.cut_off",
        tags={"conflict", "social"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="rejecter", filter=not_player),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.3,
        event_id=EventId(
            nature=EventNature.REJECTION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.HOSTILE,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.TRAINING_GROUND],
        outcomes={
            "fought": BranchOutcome(
                summary="He tried to answer the rejection. It made it worse.",
                stat_effects=[
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.03),
                    StatEffect("player", StatName.INSECURITY, 0.03),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="rejecter",
                        tension=0.12, trust=-0.06,
                    ),
                ],
                flags={"public"},
            ),
            "absorbed": BranchOutcome(
                summary="He took it. Walked away. Didn't look back.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.04),
                ],
            ),
        },
    ),
    # --- relationship.rejection.melancholy ---
    EventBlueprint(
        id="rel.fading_friendship",
        tags={"social", "vulnerability"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="former_friend", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.3,
        event_id=EventId(
            nature=EventNature.REJECTION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.MELANCHOLY,
        ),
        valid_scene_types=[SceneType.CAFE, SceneType.PARK],
        outcomes={
            "let_go": BranchOutcome(
                summary="They both knew the friendship had changed. Neither said it.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
            ),
            "clung": BranchOutcome(
                summary="He suggested next week. The pause before the answer said everything.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.03),
                ],
            ),
        },
    ),
    # --- relationship.revelation.hostile ---
    EventBlueprint(
        id="rel.overheard_truth",
        tags={"conflict", "social"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="speaker", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.3,
        event_id=EventId(
            nature=EventNature.REVELATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.HOSTILE,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.TUNNEL],
        reveals_exposure=0.15,
        outcomes={
            "confronted": BranchOutcome(
                summary="He stepped round the corner. They saw his face and stopped talking.",
                stat_effects=[
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.03),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="speaker",
                        trust=-0.10, tension=0.12,
                    ),
                ],
                flags={"public"},
            ),
            "stored": BranchOutcome(
                summary="He heard every word. He filed it away.",
                stat_effects=[
                    StatEffect("player", StatName.CAUTIOUSNESS, 0.03),
                ],
            ),
        },
    ),
    # --- relationship.revelation.tense ---
    EventBlueprint(
        id="rel.truth_slipped_out",
        tags={"social", "vulnerability"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="listener", filter=not_player),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.3,
        event_id=EventId(
            nature=EventNature.REVELATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.CAFE, SceneType.APARTMENT],
        reveals_exposure=0.1,
        outcomes={
            "owned_it": BranchOutcome(
                summary="He didn't mean to say it. But he didn't take it back.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.02),
                    StatEffect("player", StatName.INSECURITY, -0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="listener",
                        familiarity=0.06, trust=0.04,
                    ),
                ],
            ),
            "backtracked": BranchOutcome(
                summary="He laughed it off. The other person didn't.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.03),
                ],
            ),
        },
    ),
]
