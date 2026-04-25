"""Romantic events (design §8.2) — flirtation, partner tension.

Kept deliberately sparse. These are opt-in by cast availability; the filter
only passes characters with matching disposition or flag.
"""

from engine.characters import CharacterRole, TierACharacter, TierBCharacter
from engine.events import (
    BranchOutcome,
    EventBlueprint,
    RelationshipEffect,
    RoleSlot,
    SceneBlock,
    StatEffect,
)
from engine.stats import StatName

from ._helpers import is_player


_ROMANCE_ROLES = {CharacterRole.FAMILY, CharacterRole.OTHER}


def _romantic_candidate(c):
    """Named (Tier A/B) non-player reserved for romantic casting.

    Gated by role — designers author the partner character with
    `role=FAMILY` or `role=OTHER` so match rules stay explicit.
    """
    if not isinstance(c, (TierACharacter, TierBCharacter)):
        return False
    if c.id == "player":
        return False
    return c.role in _ROMANCE_ROLES


BLUEPRINTS = [
    EventBlueprint(
        id="romantic.quiet_evening",
        tags={"romantic", "downtime"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="partner", filter=_romantic_candidate),
        ],
        blocks=[SceneBlock(id="main")],
        base_weight=0.6,
        outcomes={
            "closer": BranchOutcome(
                summary=(
                    "They didn't do anything special. He left feeling better than "
                    "he'd arrived."
                ),
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, -0.03),
                    StatEffect("player", StatName.MOTIVATION, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="partner",
                        trust=0.06,
                        familiarity=0.04,
                        attraction=0.05,
                    )
                ],
            ),
            "distant": BranchOutcome(
                summary=(
                    "The conversation stayed shallow. Both of them noticed."
                ),
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.02),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="partner",
                        tension=0.04,
                    )
                ],
            ),
        },
    ),
]
