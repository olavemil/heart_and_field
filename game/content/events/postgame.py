"""Postgame events (design §8.1) — the dressing room after the whistle."""

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

from ._helpers import is_player, teammate


BLUEPRINTS = [
    EventBlueprint(
        id="postgame.win_debrief",
        tags={"postgame", "celebration"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="mate", filter=teammate(), optional=True),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you take in the win?",
            options={
                "shared": "Celebrate together",
                "private": "Process it alone",
            },
        ))],
        base_weight=0.8,
        event_id=EventId(
            nature=EventNature.CELEBRATION,
            domain=EventDomain.SPORT,
            tone=EventTone.TRIUMPHANT,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM],
        weight_modifiers=[
            WeightRule(
                predicate=lambda ctx, st: 2.2 if ctx.team_morale > 0.25 else 0.3,
                description="only fires when the team just won",
            )
        ],
        outcomes={
            "shared": BranchOutcome(
                summary=(
                    "The room was loud. He let himself be part of it for once."
                ),
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.03),
                    StatEffect("player", StatName.COLLABORATION, 0.02),
                ],
            ),
            "private": BranchOutcome(
                summary=(
                    "He packed his kit in the corner. The win hadn't caught up "
                    "with him yet."
                ),
                stat_effects=[
                    StatEffect("player", StatName.INTROSPECTION, 0.02),
                ],
            ),
        },
    ),
    EventBlueprint(
        id="postgame.loss_silence",
        tags={"postgame", "vulnerability"},
        participants=[
            RoleSlot(role="player", filter=is_player),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you handle the silence?",
            options={
                "carried": "Sit with it",
                "lashed": "Let it out",
            },
        ))],
        base_weight=0.9,
        event_id=EventId(
            nature=EventNature.CONSOLATION,
            domain=EventDomain.SPORT,
            tone=EventTone.MELANCHOLY,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM],
        weight_modifiers=[
            WeightRule(
                predicate=lambda ctx, st: 2.2 if ctx.team_morale < -0.25 else 0.2,
                description="only fires after a bad loss",
            )
        ],
        carries_arc_context=True,
        outcomes={
            "carried": BranchOutcome(
                summary=(
                    "Nobody spoke. He sat with the weight of it and didn't try "
                    "to name it."
                ),
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
            ),
            "lashed": BranchOutcome(
                summary=(
                    "He kicked the bench on the way out. Nothing about it helped."
                ),
                stat_effects=[
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.03),
                    StatEffect("player", StatName.INSECURITY, 0.03),
                ],
                flags={"public"},
            ),
        },
    ),
]
