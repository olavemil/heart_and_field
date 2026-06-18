"""Conflict events — blame, jealousy, competition (design §8.2).

Includes a simple arc (blame → apology) to exercise prereqs and
`carries_arc_context` in Phase 3's tests.
"""

from engine.event_taxonomy import EventDomain, EventType, EventNature, EventTone
from engine.events import (
    BranchOutcome,
    ChoiceNode,
    EventBlueprint,
    PlayerStance,
    RelationshipEffect,
    RoleSlot,
    SceneBlock,
    StatEffect,
    WeightRule,
)
from engine.scene_taxonomy import SceneType
from engine.secrets import AspectType
from engine.stats import StatName

from ._helpers import is_player, not_player, teammate


BLUEPRINTS = [
    EventBlueprint(
        id="conflict.blame_assignment",
        tags={"conflict", "postgame"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="target", filter=teammate()),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you respond to the blame?",
            options={
                "escalate": "Call him out",
                "hold_back": "Let it go",
            },
        ))],
        base_weight=0.4,
        # The blame lands on the player; they respond to it.
        player_stance=PlayerStance.REACTOR,
        event_id=EventType(
            nature=EventNature.CONFRONTATION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.HOSTILE,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.TRAINING_GROUND],
        boosted_by_aspects=[AspectType.HISTORY],
        reveals_exposure=0.1,
        setup=(
            "The dressing room had found its scapegoat before anyone had even "
            "showered. {name:target} said it again — louder this time, so nobody "
            "could pretend not to hear — and let the name hang in the air next to "
            "{name:player}."
        ),
        weight_modifiers=[
            WeightRule(
                predicate=lambda ctx, st: 2.0 if ctx.team_morale < -0.2 else 1.0,
                description="blame flares after a loss",
            )
        ],
        carries_arc_context=True,
        unlocks=["conflict.apology"],
        outcomes={
            "escalate": BranchOutcome(
                action_summary=(
                    "{name:player} stood, scraped the bench back, and crossed the "
                    "floor. Whatever caution {they:player} usually kept got left "
                    "behind on it."
                ),
                reaction_summary=(
                    "{name:target} didn't give an inch — chin up, voice climbing "
                    "to meet {them:player}. The others rearranged themselves into "
                    "an audience."
                ),
                summary=(
                    "{They:player} pointed a finger. The room went still; the accusation "
                    "landed wide of anyone who could deflect it."
                ),
                stat_effects=[
                    StatEffect("player", StatName.AGGRESSIVENESS, 0.03),
                    StatEffect("target", StatName.DEFENSIVENESS, 0.04),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="target",
                        tension=0.15,
                        trust=-0.08,
                    )
                ],
                flags={"unresolved", "public"},
            ),
            "hold_back": BranchOutcome(
                action_summary=(
                    "{name:player} held still. The retort built, then got folded "
                    "away somewhere it wouldn't show."
                ),
                reaction_summary=(
                    "{name:target} waited for the fight, didn't get one, and looked "
                    "almost cheated by the quiet."
                ),
                summary="{They:player} swallowed it. Said nothing. Something sat wrong.",
                stat_effects=[
                    StatEffect("player", StatName.INSECURITY, 0.02),
                    StatEffect("player", StatName.REFLECTION, 0.02),
                ],
            ),
        },
    ),
    EventBlueprint(
        id="conflict.apology",
        tags={"conflict", "resolution"},
        participants=[
            RoleSlot(role="player", filter=is_player),
            RoleSlot(role="target", filter=not_player),
        ],
        blocks=[SceneBlock(id="main", choice=ChoiceNode(
            prompt="How do you say sorry?",
            options={
                "sincere": "Mean it",
                "deflect": "Defend yourself",
            },
        ))],
        base_weight=0.7,
        event_id=EventType(
            nature=EventNature.ADMISSION,
            domain=EventDomain.RELATIONSHIP,
            tone=EventTone.MELANCHOLY,
        ),
        valid_scene_types=[SceneType.LOCKER_ROOM, SceneType.PARK],
        prerequisites=["conflict.blame_assignment"],
        carries_arc_context=True,
        setup=(
            "The thing from before still sat between them, taking up room. "
            "{name:player} found {name:target} alone — which felt like the only "
            "chance there would be to say anything at all."
        ),
        outcomes={
            "sincere": BranchOutcome(
                # A real apology thaws the room.
                result_tone=EventTone.WARM,
                action_summary=(
                    "{name:player} said the words without dressing them up. No "
                    "'but', no ledger of who had done what to whom."
                ),
                summary=(
                    "{They:player} said it plainly. No qualifiers. {name:target} looked "
                    "at the floor for a long time before answering."
                ),
                stat_effects=[
                    StatEffect("player", StatName.REFLECTION, 0.03),
                    StatEffect("target", StatName.DEFENSIVENESS, -0.03),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="target",
                        trust=0.12,
                        tension=-0.15,
                    )
                ],
            ),
            "deflect": BranchOutcome(
                # The non-apology curdles into fresh hostility.
                result_tone=EventTone.HOSTILE,
                action_summary=(
                    "{name:player} started with the apology and arrived, somehow, "
                    "at a list of reasons it had never really been {their:player} "
                    "fault."
                ),
                summary=(
                    "{Their:player} apology came wrapped in excuses. It read as another "
                    "kind of blame."
                ),
                stat_effects=[
                    StatEffect("player", StatName.DEFENSIVENESS, 0.04),
                ],
                relationship_effects=[
                    RelationshipEffect(
                        source_role="player",
                        target_role="target",
                        tension=0.05,
                    )
                ],
                flags={"unresolved"},
            ),
        },
    ),
]
