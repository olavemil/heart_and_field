"""External-pressure events (design §8.2) — media, contracts, fans."""

from engine.characters import CharacterRole
from engine.event_taxonomy import EventDomain, EventId, EventNature, EventTone
from engine.events import (
    BranchOutcome,
    ChoiceNode,
    EventBlueprint,
    RoleSlot,
    SceneBlock,
    StatEffect,
    WeightRule,
)
from engine.scene_taxonomy import SceneType
from engine.stats import StatName

from ._helpers import is_player


BLUEPRINTS = [
    EventBlueprint(
        id="external.media_scrum",
        tags={"external_pressure", "postgame"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(
                role="press",
                filter=lambda c: c.role is CharacterRole.MEDIA,
                optional=True,
            ),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you handle the questions?",
            options={
                "composed": "Stick to the script",
                "unravelled": "Say what you feel",
            },
        ))],
        base_weight=0.5,
        event_id=EventId(
            nature=EventNature.OBSERVATION,
            domain=EventDomain.INSTITUTIONAL,
            tone=EventTone.NEUTRAL,
        ),
        valid_scene_types=[SceneType.PRESS_ROOM, SceneType.STUDIO],
        reveals_exposure=0.1,
        weight_modifiers=[
            WeightRule(
                predicate=lambda ctx, st: 1.6 if ctx.team_morale < -0.2 else 1.0,
                description="media heat up after a loss",
            )
        ],
        outcomes={
            "composed": BranchOutcome(
                summary=(
                    "{They:player} answered the questions the way {they:player}'d been "
                    "told to. It came out sounding almost true."
                ),
                stat_effects=[
                    StatEffect("player", StatName.CAUTIOUSNESS, 0.02),
                ],
                flags={"public"},
            ),
            "unravelled": BranchOutcome(
                summary=(
                    "Someone asked the wrong question. {They:player} gave them the "
                    "answer they were looking for."
                ),
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.04),
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.02),
                ],
                flags={"public", "quotable"},
            ),
        },
    ),
    EventBlueprint(
        id="external.contract_talk",
        tags={"external_pressure", "downtime"},
        participants=[
            RoleSlot(role="player", filter=is_player),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="What's your approach?",
            options={
                "focused": "Take your time",
                "rattled": "Let it worry you",
            },
        ))],
        base_weight=0.3,
        carries_arc_context=True,
        event_id=EventId(
            nature=EventNature.NEGOTIATION,
            domain=EventDomain.INSTITUTIONAL,
            tone=EventTone.TENSE,
        ),
        valid_scene_types=[SceneType.OFFICE],
        outcomes={
            "focused": BranchOutcome(
                summary=(
                    "The agent called. {They:player} listened and said {they:player}'d "
                    "think about it."
                ),
                stat_effects=[
                    StatEffect("player", StatName.MOTIVATION, 0.02),
                ],
            ),
            "rattled": BranchOutcome(
                summary=(
                    "The numbers weren't the problem. {They:player} couldn't get the "
                    "tone of the call out of {their:player} head."
                ),
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.05),
                ],
            ),
        },
    ),
]
