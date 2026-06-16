"""Apartment scene graph: entrance hub, living room, kitchen, bathroom,
bedroom, balcony.

A flat reads tighter than a house — the entrance opens straight onto the
living room, with the kitchen, bathroom, and bedroom off it and a balcony
beyond the living room. Hot-tier residence (Phase 23): 3 alternates per
room.
"""

from engine.background_pool import LocationKind, SceneGraphSpec


SPECS = [
    SceneGraphSpec(
        spec_id="apartment",
        kind=LocationKind.APARTMENT,
        nodes=(
            "entrance",
            "living_room",
            "kitchen",
            "bathroom",
            "bedroom",
            "balcony",
        ),
        adjacency=(
            ("entrance", "living_room"),
            ("living_room", "kitchen"),
            ("living_room", "bathroom"),
            ("living_room", "bedroom"),
            ("living_room", "balcony"),
        ),
        entry_nodes=("entrance",),
        alternates=(
            ("entrance", 3),
            ("living_room", 3),
            ("kitchen", 3),
            ("bathroom", 3),
            ("bedroom", 3),
            ("balcony", 3),
        ),
    ),
]
