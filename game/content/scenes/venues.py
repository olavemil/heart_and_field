"""Standalone hot-tier venues: training ground, match pitch, cafe.

Each is a small graph the story enters directly (single node, or the two
cafe styles). Match-day arena colour variants and the rest of the
generic catalogue land in a later pass; this is the hot-tier prototype
set (Phase 23).
"""

from engine.background_pool import LocationKind, SceneGraphSpec


SPECS = [
    # Outdoor training pitch — its own kind so the prompt reads
    # "training ground" rather than the contradictory "gym".
    SceneGraphSpec(
        spec_id="training_ground",
        kind=LocationKind.TRAINING_GROUND,
        nodes=("training_ground",),
        entry_nodes=("training_ground",),
        alternates=(("training_ground", 3),),
    ),
    # Match pitch — neutral colour for the prototype; team-colour
    # variants + stands/tunnel arrive with the full arena set.
    SceneGraphSpec(
        spec_id="pitch",
        kind=LocationKind.STADIUM,
        nodes=("pitch",),
        entry_nodes=("pitch",),
        alternates=(("pitch", 3),),
    ),
    # Cafe, two styles the story can enter: a coffee shop and a bakery.
    SceneGraphSpec(
        spec_id="cafe",
        kind=LocationKind.CAFE,
        nodes=("coffee_shop", "bakery"),
        entry_nodes=("coffee_shop", "bakery"),
        alternates=(("coffee_shop", 3), ("bakery", 3)),
    ),
    # --- Tier-1 coverage gaps (Phase 23E) -------------------------------
    # Events already fire in these scene types but resolved to the wrong
    # background (team night out -> a cafe; media scrum -> a school) or to
    # nothing (travel -> blank). Each is a single-node spec; the bridge
    # funnels related scene types in (club -> bar, studio -> media,
    # car/plane -> transit).
    SceneGraphSpec(
        spec_id="bar",
        kind=LocationKind.BAR,
        nodes=("bar",),
        entry_nodes=("bar",),
        alternates=(("bar", 2),),
    ),
    SceneGraphSpec(
        spec_id="media",
        kind=LocationKind.MEDIA,
        nodes=("press_room",),
        entry_nodes=("press_room",),
        alternates=(("press_room", 2),),
    ),
    SceneGraphSpec(
        spec_id="transit",
        kind=LocationKind.TRANSIT,
        nodes=("team_bus",),
        entry_nodes=("team_bus",),
        alternates=(("team_bus", 2),),
    ),
]
