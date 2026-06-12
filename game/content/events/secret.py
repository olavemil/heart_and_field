"""Secret-domain events — require secret membership to trigger."""

from engine.event_taxonomy import EventDomain, EventId, EventNature, EventTone
from engine.events import (
    BranchOutcome,
    ChoiceNode,
    EventBlueprint,
    RelationshipEffect,
    RoleSlot,
    SceneBlock,
    StatEffect,
)
from engine.scene_taxonomy import SceneType
from engine.secrets import AspectType, SecretRole
from engine.stats import StatName

from ._helpers import is_player, not_player, teammate


BLUEPRINTS = [
    # --- secret.observation.neutral ---
    EventBlueprint(
        id="secret.noticed_something",
        tags={"social", "secret"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="subject", filter=not_player),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="Do you acknowledge what you saw?",
            options={
                "filed_away": "Let the moment pass",
                "overlooked": "Miss it entirely",
            },
        ))],
        base_weight=0.4,
        event_id=EventId(
            nature=EventNature.OBSERVATION,
            domain=EventDomain.SECRET,
            tone=EventTone.NEUTRAL,
        ),
        valid_scene_types=[SceneType.CAFE, SceneType.LOCKER_ROOM, SceneType.PARK],
        requires_aspects=[AspectType.RELATIONSHIP],
        reveals_exposure=0.1,
        outcomes={
            "filed_away": BranchOutcome(
                summary="He noticed the look between them. He didn't say anything.",
                stat_effects=[
                    StatEffect("player", StatName.INTROSPECTION, 0.02),
                ],
            ),
            "overlooked": BranchOutcome(
                summary="It was right there. He missed it.",
                stat_effects=[],
            ),
        },
    ),
    # --- secret.confrontation.tense ---
    EventBlueprint(
        id="secret.quiet_accusation",
        tags={"conflict", "secret"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="suspect", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you approach this?",
            options={
                "probed": "Ask carefully",
                "retreated": "Back away",
            },
        ))],
        base_weight=0.3,
        event_id=EventId(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.SECRET,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.APARTMENT],
        requires_secret_role=SecretRole.OWNER,
        reveals_exposure=0.15,
        outcomes={
            "probed": BranchOutcome(
                summary="He asked a careful question. The answer told him more than the words.",
                stat_effects=[
                    StatEffect("player", StatName.CAUTIOUSNESS, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="suspect",
                        tension=0.06, familiarity=0.03,
                    ),
                ],
            ),
            "retreated": BranchOutcome(
                summary="He started to ask, then changed the subject.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
            ),
        },
    ),
    # --- secret.confrontation.hostile ---
    EventBlueprint(
        id="secret.exposed",
        tags={"conflict", "secret"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="accuser", filter=not_player),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="Do you defend yourself?",
            options={
                "denied": "Deny it flatly",
                "admitted": "Admit the truth",
            },
        ))],
        base_weight=0.2,
        event_id=EventId(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.SECRET,
            tone=EventTone.HOSTILE,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.OFFICE],
        requires_secret_role=SecretRole.OWNER,
        reveals_exposure=0.25,
        outcomes={
            "denied": BranchOutcome(
                summary="He looked them in the eye and said it wasn't true. They both knew it was.",
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.04),
                    StatEffect("player", StatName.INSECURITY, 0.03),
                ],
                flags={"public"},
            ),
            "admitted": BranchOutcome(
                summary="He didn't fight it. He let the truth sit there.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.02),
                    StatEffect("player", StatName.INSECURITY, -0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="accuser",
                        trust=0.06, tension=-0.04,
                    ),
                ],
            ),
        },
    ),
    # --- secret.admission.melancholy ---
    EventBlueprint(
        id="secret.confided",
        tags={"vulnerability", "secret"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="confidant", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How much do you tell them?",
            options={
                "trusted": "Tell them most of it",
                "regretted": "Say too much",
            },
        ))],
        base_weight=0.3,
        event_id=EventId(
            nature=EventNature.ADMISSION,
            domain=EventDomain.SECRET,
            tone=EventTone.MELANCHOLY,
        ),
        valid_scene_types=[SceneType.APARTMENT, SceneType.CAR],
        requires_secret_role=SecretRole.OWNER,
        reveals_exposure=0.2,
        carries_arc_context=True,
        outcomes={
            "trusted": BranchOutcome(
                summary="He told them. Not all of it. Enough.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, -0.03),
                    StatEffect("player", StatName.REFLECTION, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="confidant",
                        trust=0.10, familiarity=0.06,
                    ),
                ],
            ),
            "regretted": BranchOutcome(
                summary="He said too much. The walk home was long.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.04),
                ],
            ),
        },
    ),
    # --- secret.admission.romantic ---
    EventBlueprint(
        id="secret.romantic_secret",
        tags={"romantic", "secret"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="partner", filter=not_player),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.2,
        event_id=EventId(
            nature=EventNature.ADMISSION,
            domain=EventDomain.SECRET,
            tone=EventTone.ROMANTIC,
        ),
        valid_scene_types=[SceneType.APARTMENT, SceneType.PARK],
        requires_aspects=[AspectType.RELATIONSHIP],
        reveals_exposure=0.2,
        outcomes={
            "received_well": BranchOutcome(
                summary="He told them the part he'd been holding back. They didn't flinch.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.03),
                    StatEffect("player", StatName.INSECURITY, -0.03),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="partner",
                        trust=0.10, attraction=0.05,
                    ),
                ],
            ),
            "too_much": BranchOutcome(
                summary="The honesty landed wrong. Something shifted in the air.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.04),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="partner",
                        tension=0.06,
                    ),
                ],
            ),
        },
    ),
    # --- secret.revelation.hostile ---
    EventBlueprint(
        id="secret.forced_reveal",
        tags={"conflict", "secret"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="revealer", filter=not_player),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.2,
        event_id=EventId(
            nature=EventNature.REVELATION,
            domain=EventDomain.SECRET,
            tone=EventTone.HOSTILE,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.PRESS_ROOM],
        requires_aspects=[AspectType.TABOO],
        reveals_exposure=0.3,
        outcomes={
            "damage_control": BranchOutcome(
                summary="He got ahead of it. Barely.",
                stat_effects=[
                    StatEffect("player", StatName.CAUTIOUSNESS, 0.03),
                ],
                flags={"public"},
            ),
            "overwhelmed": BranchOutcome(
                summary="Everyone knew before he could explain. The room shifted around him.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.05),
                    StatEffect("player", StatName.CONFIDENCE, -0.03),
                ],
                flags={"public"},
            ),
        },
    ),
    # --- secret.revelation.tense ---
    EventBlueprint(
        id="secret.discovered",
        tags={"social", "secret"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="discovered_by", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.3,
        event_id=EventId(
            nature=EventNature.REVELATION,
            domain=EventDomain.SECRET,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.APARTMENT],
        requires_secret_role=SecretRole.OWNER,
        reveals_exposure=0.2,
        outcomes={
            "explained": BranchOutcome(
                summary="He saw their face change. He started talking before they could ask.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="discovered_by",
                        familiarity=0.06, trust=0.04,
                    ),
                ],
            ),
            "stonewalled": BranchOutcome(
                summary="He pretended nothing happened. They let him.",
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.03),
                ],
            ),
        },
    ),
    # --- secret.negotiation.tense ---
    EventBlueprint(
        id="secret.leverage_play",
        tags={"conflict", "secret"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="counterpart", filter=not_player),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.2,
        event_id=EventId(
            nature=EventNature.NEGOTIATION,
            domain=EventDomain.SECRET,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.OFFICE, SceneType.CAFE],
        requires_aspects=[AspectType.AGENDA],
        outcomes={
            "gained_ground": BranchOutcome(
                summary="He used what he knew. The other person's expression changed.",
                stat_effects=[
                    StatEffect("player", StatName.CAUTIOUSNESS, 0.03),
                    StatEffect("player", StatName.CONFIDENCE, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player", target_role="counterpart",
                        tension=0.08, trust=-0.04,
                    ),
                ],
            ),
            "overplayed": BranchOutcome(
                summary="He showed his hand too early. The silence that followed was expensive.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.04),
                ],
            ),
        },
    ),
    # --- secret.isolation.melancholy ---
    EventBlueprint(
        id="secret.carrying_alone",
        tags={"solo", "secret", "vulnerability"},
        participants=[RoleSlot(role="player", filter=is_player)],
        blocks=[SceneBlock(id="main")],
        base_weight=0.3,
        event_id=EventId(
            nature=EventNature.ISOLATION,
            domain=EventDomain.SECRET,
            tone=EventTone.MELANCHOLY,
        ),
        valid_scene_types=[SceneType.APARTMENT, SceneType.HOUSE],
        requires_secret_role=SecretRole.OWNER,
        outcomes={
            "endured": BranchOutcome(
                summary="He sat with what he couldn't tell anyone. The flat was very quiet.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
            ),
            "numb": BranchOutcome(
                summary="He'd carried it so long it didn't feel like anything anymore.",
                stat_effects=[
                    StatEffect("player", StatName.INTROSPECTION, 0.02),
                ],
            ),
        },
    ),
]
