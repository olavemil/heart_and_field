"""Mentor and rivalry events (design §8.2).

Mentor and rival arcs run on long cadence — low base weight plus
`carries_arc_context` so the accumulated summary gains weight each fire.
"""

from engine.characters import CharacterRole
from engine.events import (
    BranchOutcome,
    EventBlueprint,
    LocationCue,
    RelationshipEffect,
    RoleSlot,
    SceneBlock,
    StatEffect,
)
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
        blocks=[SceneBlock(id="main")],
        base_weight=0.5,
        carries_arc_context=True,
        location=LocationCue(
            spec_id="school",
            node_name="locker_bay",
            graph_id="main_school",
        ),
        outcomes={
            "lands": BranchOutcome(
                summary=(
                    "The older man said something short and then went back to "
                    "his boots. It stayed with him."
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
                summary=(
                    "He heard the words. He decided he already knew them."
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
        blocks=[SceneBlock(id="main")],
        base_weight=0.4,
        carries_arc_context=True,
        outcomes={
            "meets_it": BranchOutcome(
                summary=(
                    "He looked {name:rival} in the eye and didn't move first. "
                    "Neither did the other man."
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
                    "He let it slide. He told himself it didn't matter. It did."
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
