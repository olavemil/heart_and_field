"""Mentor and rivalry events (design §8.2).

Mentor and rival arcs run on long cadence — low base weight plus
`carries_arc_context` so the accumulated summary gains weight each fire.
"""

from engine.characters import CharacterRole
from engine.event_taxonomy import EventDomain, EventType, EventNature, EventTone
from engine.events import (
    BranchOutcome,
    ChoiceNode,
    EventBlueprint,
    LocationCue,
    PlayerStance,
    RelationshipEffect,
    RoleSlot,
    SceneBlock,
    StatEffect,
)
from engine.scene_taxonomy import SceneType
from engine.secrets import AspectType
from engine.stats import StatName

from ._helpers import is_player, teammate


def _senior_pro(c):
    """A teammate with seniority — proxy via leadership stat value."""
    from engine.characters import TierACharacter, TierBCharacter
    from engine.stats import StatName as SN, StatTuple

    if not isinstance(c, (TierACharacter, TierBCharacter)) or c.id == "player":
        return False
    lead = c.stats.get(SN.LEADERSHIP)
    if isinstance(lead, StatTuple):
        return lead.value > 0.6
    if isinstance(lead, (int, float)):
        return float(lead) > 0.6
    return False


BLUEPRINTS = [
    EventBlueprint(
        id="mentor.quiet_word",
        tags={"mentor", "downtime"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="mentor", filter=_senior_pro),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="Do you hear him out?",
            options={
                "lands": "Take it to heart",
                "brushed_off": "Dismiss it",
            },
        ))],
        base_weight=0.5,
        carries_arc_context=True,
        # The mentor speaks; the player takes it in or doesn't.
        player_stance=PlayerStance.REACTOR,
        event_id=EventType(
            nature=EventNature.CONSOLATION,
            domain=EventDomain.RELATIONSHIP,
            # A mentor's quiet word: warm, or weighted with melancholy.
            possible_tones={EventTone.WARM, EventTone.MELANCHOLY},
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.TRAINING_GROUND],
        boosted_by_aspects=[AspectType.HISTORY],
        location=LocationCue(
            spec_id="school",
            node_name="locker_bay",
            graph_id="main_school",
        ),
        setup=(
            "The bay had cleared out except for {name:mentor}, unhurried over a "
            "pair of boots. {name:mentor} waited until {name:player} was within "
            "earshot before saying anything, the way the old pros always seemed to."
        ),
        outcomes={
            "lands": BranchOutcome(
                action_summary=(
                    "{name:player} stopped, actually stopped, and let the advice "
                    "land instead of bouncing off the usual armour."
                ),
                summary=(
                    "{name:mentor} said something short and then went back to "
                    "{their:mentor} boots. It stayed with {them:player}."
                ),
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                    StatEffect("player", StatName.CONFIDENCE, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="mentor",
                        trust=0.06,
                        familiarity=0.03,
                    )
                ],
            ),
            "brushed_off": BranchOutcome(
                action_summary=(
                    "{name:player} nodded along on the outside and had already "
                    "filed it under things {they:player} did not need to hear."
                ),
                summary=(
                    "{They:player} heard the words. {They:player} decided {they:player} already knew them."
                ),
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.03),
                ],
            ),
        },
    ),
    EventBlueprint(
        id="rival.challenge",
        tags={"rival", "conflict"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="rival", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you respond?",
            options={
                "meets_it": "Hold his gaze",
                "backs_down": "Walk away",
            },
        ))],
        base_weight=0.4,
        carries_arc_context=True,
        # The rival throws down; the player responds.
        player_stance=PlayerStance.REACTOR,
        event_id=EventType(
            nature=EventNature.COMPETITION,
            domain=EventDomain.RELATIONSHIP,
            # A rival's challenge: taut, or openly hostile.
            possible_tones={EventTone.TENSE, EventTone.HOSTILE},
        ),
        valid_scene_types=[SceneType.TRAINING_GROUND, SceneType.PITCH],
        outcomes={
            "meets_it": BranchOutcome(
                summary=(
                    "{They:player} looked {name:rival} in the eye and didn't move first. "
                    "Neither did {they:rival}."
                ),
                stat_effects=[
                    StatEffect("player", StatName.CONFIDENCE, 0.03),
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="rival",
                        tension=0.08,
                        familiarity=0.02,
                    )
                ],
            ),
            "backs_down": BranchOutcome(
                summary=(
                    "{They:player} let it slide. {They:player} told {themself:player} it didn't matter. It did."
                ),
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.04),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="rival",
                        tension=0.04,
                    )
                ],
            ),
        },
    ),
]
