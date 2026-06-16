"""Pregame events (design §8.1) — the dressing room, rituals, nerves."""

from engine.event_taxonomy import EventDomain, EventId, EventNature, EventTone
from engine.events import (
    BranchOutcome,
    ChoiceNode,
    EventBlueprint,
    RoleSlot,
    SceneBlock,
    StatEffect,
)
from engine.scene_taxonomy import SceneType
from engine.stats import StatName

from ._helpers import is_player, teammate


BLUEPRINTS = [
    EventBlueprint(
        id="pregame.locker_room_speech",
        tags={"pregame", "leadership"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(
                role="speaker",
                filter=lambda c: c.role.value in {"manager", "midfielder", "defender"},
            ),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="What's your message?",
            options={
                "rousing": "Fire them up",
                "flat": "Keep it brief",
            },
        ))],
        base_weight=1.0,
        event_id=EventId(
            nature=EventNature.COLLABORATION,
            domain=EventDomain.SPORT,
            tone=EventTone.WARM,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.TUNNEL],
        outcomes={
            "rousing": BranchOutcome(
                summary="The speech worked. The room leaned in.",
                stat_effects=[
                    StatEffect("player", StatName.MOTIVATION, 0.05),
                    StatEffect("player", StatName.CONFIDENCE, 0.02),
                ],
                flags={"public"},
            ),
            "flat": BranchOutcome(
                summary=(
                    "Whatever the speech was supposed to do, it didn't. The "
                    "room stayed quiet."
                ),
                stat_effects=[
                    StatEffect("player", StatName.MOTIVATION, -0.02),
                ],
            ),
        },
    ),
    EventBlueprint(
        id="pregame.ritual",
        tags={"pregame", "solo"},
        participants=[RoleSlot(role="player", filter=is_player)],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="Run through your ritual?",
            options={
                "centred": "Really focus on it",
                "hollow": "Go through the motions",
            },
        ))],
        base_weight=0.7,
        event_id=EventId(
            nature=EventNature.ISOLATION,
            domain=EventDomain.PERSONAL,
            tone=EventTone.MELANCHOLY,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM],
        outcomes={
            "centred": BranchOutcome(
                summary="The ritual worked. {They:player} felt ready.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.03),
                    StatEffect("player", StatName.INSECURITY, -0.02),
                ],
            ),
            "hollow": BranchOutcome(
                summary=(
                    "{They:player} went through the motions. It didn't feel the way it "
                    "was supposed to."
                ),
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
            ),
        },
    ),
]
