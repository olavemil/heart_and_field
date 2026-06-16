"""Team HQ scene graph: locker room hub, recreation area, showers,
manager's office, conference room.

Sport-agnostic club interior — the player sees one HQ across a
playthrough. The locker room is the hub the others branch off. Kind is
TEAM_HQ so the prompt's container word ("team hq") fits all five diverse
rooms; per-room hints carry the specifics. Hot-tier (Phase 23): locker
room — the single most frequently visited scene — gets 3 alternates; the
rest get 2.
"""

from engine.background_pool import LocationKind, SceneGraphSpec


SPECS = [
    SceneGraphSpec(
        spec_id="team_hq",
        kind=LocationKind.TEAM_HQ,
        nodes=(
            "locker_room",
            "recreation",
            "showers",
            "manager_office",
            "conference_room",
        ),
        adjacency=(
            ("locker_room", "showers"),
            ("locker_room", "recreation"),
            ("locker_room", "manager_office"),
            ("locker_room", "conference_room"),
        ),
        entry_nodes=("locker_room",),
        alternates=(
            ("locker_room", 3),
            ("recreation", 2),
            ("showers", 2),
            ("manager_office", 2),
            ("conference_room", 2),
        ),
    ),
]
