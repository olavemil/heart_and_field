"""Suburban house scene graph: front door entry, living room hub, kitchen,
hallway, bathroom, bedroom.

The hub-and-spokes shape mirrors how the story moves through someone's
home — most rooms branch off the living room, the bathroom is reached
through the hallway, and the bedroom sits at the end of the hall.
"""

from engine.background_pool import LocationKind, SceneGraphSpec


SPECS = [
    SceneGraphSpec(
        spec_id="suburban_house",
        kind=LocationKind.SUBURBAN_HOUSE,
        nodes=(
            "front_door",
            "living_room",
            "kitchen",
            "hallway",
            "bathroom",
            "bedroom",
        ),
        adjacency=(
            ("front_door", "living_room"),
            ("living_room", "kitchen"),
            ("living_room", "hallway"),
            ("hallway", "bathroom"),
            ("hallway", "bedroom"),
        ),
        entry_nodes=("front_door",),
    ),
]
