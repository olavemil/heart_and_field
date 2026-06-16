"""Suburban house scene graph: garden + front door entry, living room hub,
kitchen, hallway, bathroom, bedroom.

The hub-and-spokes shape mirrors how the story moves through someone's
home — most rooms branch off the living room, the bathroom and bedroom
are reached through the hallway, and the garden sits outside the front
door. A hot-tier residence (Phase 23): every room carries 3 alternates
so frequent visits don't repeat the same shot.
"""

from engine.background_pool import LocationKind, SceneGraphSpec


SPECS = [
    SceneGraphSpec(
        spec_id="suburban_house",
        kind=LocationKind.SUBURBAN_HOUSE,
        nodes=(
            "garden",
            "front_door",
            "living_room",
            "kitchen",
            "hallway",
            "bathroom",
            "bedroom",
        ),
        adjacency=(
            ("garden", "front_door"),
            ("front_door", "living_room"),
            ("living_room", "kitchen"),
            ("living_room", "hallway"),
            ("hallway", "bathroom"),
            ("hallway", "bedroom"),
        ),
        entry_nodes=("front_door",),
        alternates=(
            ("garden", 3),
            ("front_door", 3),
            ("living_room", 3),
            ("kitchen", 3),
            ("hallway", 3),
            ("bathroom", 3),
            ("bedroom", 3),
        ),
    ),
]
