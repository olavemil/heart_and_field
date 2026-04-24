"""Pregame events (design §8.1) — the dressing room, rituals, nerves."""

from engine.events import (
    BranchOutcome,
    EventBlueprint,
    RoleSlot,
    SceneBlock,
    StatEffect,
)
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
        blocks=[SceneBlock(id="main")],
        base_weight=1.0,
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
        blocks=[SceneBlock(id="main")],
        base_weight=0.7,
        outcomes={
            "centred": BranchOutcome(
                summary="The ritual worked. He felt ready.",
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.03),
                    StatEffect("player", StatName.INSECURITY, -0.02),
                ],
            ),
            "hollow": BranchOutcome(
                summary=(
                    "He went through the motions. It didn't feel the way it "
                    "was supposed to."
                ),
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
            ),
        },
    ),
]
