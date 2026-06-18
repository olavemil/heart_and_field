"""Institutional-domain events — front office, media, board politics."""

from engine.event_taxonomy import EventDomain, EventId, EventNature, EventTone
from engine.events import (
    BranchOutcome,
    ChoiceNode,
    EventBlueprint,
    PlayerStance,
    RelationshipEffect,
    RoleSlot,
    SceneBlock,
    StatEffect,
)
from engine.scene_taxonomy import SceneType
from engine.stats import StatName

from ._helpers import is_player, not_player


BLUEPRINTS = [
    # --- institutional.celebration.triumphant ---
    EventBlueprint(
        id="inst.award_ceremony",
        tags={"institutional", "celebration"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="presenter", filter=not_player, optional=True),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you receive this?",
            options={
                "gracious": "Thank them sincerely",
                "hollow": "Dwell on the cost",
            },
        ))],
        base_weight=0.3,
        # The honour is conferred on the player; they receive it.
        player_stance=PlayerStance.REACTOR,
        event_id=EventId(
            nature=EventNature.CELEBRATION,
            domain=EventDomain.INSTITUTIONAL,
            tone=EventTone.TRIUMPHANT,
        ),
        valid_scene_types=[SceneType.BOARDROOM, SceneType.PRESS_ROOM],
        outcomes={
            "gracious": BranchOutcome(
                summary="{They:player} thanked the right people, the expected ones. The room clapped.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.03),
                    StatEffect("player", StatName.LEADERSHIP, 0.02),
                ],
                flags={"public"},
            ),
            "hollow": BranchOutcome(
                summary="The trophy was heavier than expected. Lighter than what it cost.",
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                ],
            ),
        },
    ),
    # --- institutional.confrontation.hostile ---
    EventBlueprint(
        id="inst.board_clash",
        tags={"institutional", "conflict"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="official",
                     filter=lambda c: c.role.value in {"manager", "media", "other"}),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="What's your move?",
            options={
                "defiant": "Speak your mind",
                "complied": "Sign as instructed",
            },
        ))],
        base_weight=0.3,
        event_id=EventId(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.INSTITUTIONAL,
            tone=EventTone.HOSTILE,
        ),
        valid_scene_types=[SceneType.OFFICE, SceneType.BOARDROOM],
        outcomes={
            "defiant": BranchOutcome(
                summary="{They:player} said what {they:player} thought about the decision. The room went cold.",
                stat_effects=[
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.03),
                    StatEffect("player", StatName.LEADERSHIP, 0.02),
                ],
                flags={"public"},
            ),
            "complied": BranchOutcome(
                summary="{They:player} signed where indicated. {Their:player} hand was steady.",
                stat_effects=[
                    StatEffect("player", StatName.CAUTIOUSNESS, 0.03),
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
            ),
        },
    ),
    # --- institutional.isolation.tense ---
    EventBlueprint(
        id="inst.suspended",
        tags={"institutional", "solo"},
        participants=[RoleSlot(role="player", filter=is_player)],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How will you spend this?",
            options={
                "stewed": "Wait for your chance",
                "used_it": "Make it productive",
            },
        ))],
        base_weight=0.2,
        event_id=EventId(
            nature=EventNature.ISOLATION,
            domain=EventDomain.INSTITUTIONAL,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.APARTMENT, SceneType.HOUSE],
        outcomes={
            "stewed": BranchOutcome(
                summary="The phone didn't ring. {They:player} checked it anyway.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.04),
                    StatEffect("player", StatName.REFLECTION, 0.02),
                ],
            ),
            "used_it": BranchOutcome(
                summary="The time off was enforced. {They:player} filled it with something useful.",
                stat_effects=[
                    StatEffect("player", StatName.INTROSPECTION, 0.03),
                ],
            ),
        },
    ),
    # --- institutional.negotiation.hostile ---
    EventBlueprint(
        id="inst.transfer_demand",
        tags={"institutional", "conflict"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="official",
                     filter=lambda c: c.role.value in {"manager", "other"}),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you negotiate?",
            options={
                "held_firm": "Hold your ground",
                "caved": "Accept their terms",
            },
        ))],
        base_weight=0.2,
        event_id=EventId(
            nature=EventNature.NEGOTIATION,
            domain=EventDomain.INSTITUTIONAL,
            tone=EventTone.HOSTILE,
        ),
        valid_scene_types=[SceneType.OFFICE, SceneType.BOARDROOM],
        outcomes={
            "held_firm": BranchOutcome(
                summary="{They:player} repeated {their:player} position. The silence stretched.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.02),
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.02),
                ],
            ),
            "caved": BranchOutcome(
                summary="{They:player} agreed to the terms. The walk to the car park was long.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.04),
                ],
            ),
        },
    ),
    # --- institutional.revelation.tense ---
    EventBlueprint(
        id="inst.leaked_news",
        tags={"institutional", "external_pressure"},
        participants=[
            RoleSlot(role="player", filter=is_player),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="What's your strategy?",
            options={
                "prepared": "Get ahead of it",
                "blindsided": "Let it break",
            },
        ))],
        base_weight=0.3,
        event_id=EventId(
            nature=EventNature.REVELATION,
            domain=EventDomain.INSTITUTIONAL,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.APARTMENT, SceneType.LOCKER_ROOM],
        reveals_exposure=0.15,
        outcomes={
            "prepared": BranchOutcome(
                summary="{They:player} saw the headline before anyone asked. {They:player} had {their:player} answer ready.",
                stat_effects=[
                    StatEffect("player", StatName.CAUTIOUSNESS, 0.03),
                ],
            ),
            "blindsided": BranchOutcome(
                summary="Someone showed {them:player} the article. {They:player} read it twice.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.04),
                ],
            ),
        },
    ),
]
