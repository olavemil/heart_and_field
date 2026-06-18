"""Romantic events (design §8.2) — flirtation, partner tension.

Kept deliberately sparse. These are opt-in by cast availability; the filter
only passes characters with matching disposition or flag.
"""

from engine.characters import CharacterRole, TierACharacter, TierBCharacter
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
from engine.secrets import AspectType
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
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you spend the evening?",
            options={
                "closer": "Let your guard down",
                "distant": "Keep things light",
            },
        ))],
        base_weight=0.6,
        event_id=EventId(
            nature=EventNature.INVITATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.ROMANTIC,
        ),
        valid_scene_types=[
            SceneType.RESTAURANT, SceneType.CAFE, SceneType.PARK,
            SceneType.APARTMENT,
        ],
        boosted_by_aspects=[AspectType.RELATIONSHIP, AspectType.AGENDA],
        setup=(
            "The evening had no agenda and nowhere to be. {name:partner} sat close "
            "enough that the small talk kept running out, and the pauses started "
            "doing more of the talking than either of them."
        ),
        outcomes={
            "closer": BranchOutcome(
                action_summary=(
                    "{name:player} stopped performing for a moment and just answered "
                    "honestly, the way {they:player} rarely let {themself:player}."
                ),
                reaction_summary=(
                    "{name:partner} noticed the shift and met it, and the distance "
                    "between them quietly stopped needing managing."
                ),
                summary=(
                    "They didn't do anything special. {They:player} left feeling better than "
                    "{they:player}'d arrived."
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
                action_summary=(
                    "{name:player} kept it to easy ground — jokes, scores, the "
                    "safe stuff — and let the real thing stay unsaid."
                ),
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
