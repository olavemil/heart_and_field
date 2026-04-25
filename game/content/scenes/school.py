"""School scene graph: courtyard entry, hallway, classroom, locker bay,
gym, principal's office.
"""

from engine.background_pool import LocationKind, SceneGraphSpec


SPECS = [
    SceneGraphSpec(
        spec_id="school",
        kind=LocationKind.SCHOOL,
        nodes=(
            "courtyard",
            "hallway",
            "classroom",
            "locker_bay",
            "gym",
            "office",
        ),
        adjacency=(
            ("courtyard", "hallway"),
            ("hallway", "classroom"),
            ("hallway", "locker_bay"),
            ("hallway", "gym"),
            ("hallway", "office"),
        ),
        entry_nodes=("courtyard",),
    ),
]
