"""Scene taxonomy (addendum §4.1–§4.2) — Phase 16.

Three-layer hierarchy for narrative scene placement:

- ``SceneCategory`` — coarse intent (sport / social / private / transit
  / media / institutional). Drives broad event-domain routing.
- ``SceneType`` — concrete location kind (locker_room, bar, hotel_room,
  press_room, …). Authored on event blueprints via
  ``EventBlueprint.valid_scene_types`` (Phase 17).
- ``SceneInstance`` — styled variant of a ``SceneType`` (BAR_LOCAL vs
  BAR_UPSCALE, APARTMENT_SHARED vs APARTMENT_SOLO). Authored on event
  blueprints via ``EventBlueprint.preferred_instances``.

``SCENE_ADJACENCY`` is the global graph that lets event chaining
("a confrontation in the bar continues at the bar counter") pick a
plausible follow-up location.

This module is **separate from** ``engine.background_pool``'s
``LocationKind``. ``LocationKind`` describes what an *image* looks
like (visual pipeline); ``SceneType`` describes what a *scene* means
(narrative pipeline). The bridge :func:`location_kind_for_scene_type`
lets event-driven content tag scenes via ``SceneType`` while still
hooking into the existing background generator.
"""

from __future__ import annotations

from enum import Enum

from .background_pool import LocationKind


# ===========================================================================
# Categories
# ===========================================================================


class SceneCategory(str, Enum):
    SPORT = "sport"
    SOCIAL = "social"
    PRIVATE = "private"
    TRANSIT = "transit"
    MEDIA = "media"
    INSTITUTIONAL = "institutional"


# ===========================================================================
# Concrete scene types (addendum §4.1 verbatim)
# ===========================================================================


class SceneType(str, Enum):
    # SPORT
    PITCH = "pitch"
    TRAINING_GROUND = "training_ground"
    GYM = "gym"
    LOCKER_ROOM = "locker_room"
    STANDS = "stands"
    TUNNEL = "tunnel"
    MEDICAL = "medical"
    # SOCIAL
    RESTAURANT = "restaurant"
    BAR = "bar"
    CAFE = "cafe"
    CLUB = "club"
    PARK = "park"
    POOL = "pool"
    BEACH = "beach"
    PARTY_VENUE = "party_venue"
    # PRIVATE
    APARTMENT = "apartment"
    HOUSE = "house"
    MANSION = "mansion"
    COMPOUND = "compound"
    HOTEL_ROOM = "hotel_room"
    # TRANSIT
    BUS = "bus"
    PLANE = "plane"
    CAR = "car"
    STATION = "station"
    AIRPORT = "airport"
    # MEDIA
    PRESS_ROOM = "press_room"
    STUDIO = "studio"
    PHOTO_SHOOT = "photo_shoot"
    # INSTITUTIONAL
    OFFICE = "office"
    BOARDROOM = "boardroom"
    HOSPITAL = "hospital"
    COURTROOM = "courtroom"


# Categorisation lookup. Authored alongside the enum so the (category,
# type) relation is explicit and discoverable; never inferred from
# string prefixes.
SCENE_CATEGORY: dict[SceneType, SceneCategory] = {
    # Sport
    SceneType.PITCH:           SceneCategory.SPORT,
    SceneType.TRAINING_GROUND: SceneCategory.SPORT,
    SceneType.GYM:             SceneCategory.SPORT,
    SceneType.LOCKER_ROOM:     SceneCategory.SPORT,
    SceneType.STANDS:          SceneCategory.SPORT,
    SceneType.TUNNEL:          SceneCategory.SPORT,
    SceneType.MEDICAL:         SceneCategory.SPORT,
    # Social
    SceneType.RESTAURANT:      SceneCategory.SOCIAL,
    SceneType.BAR:             SceneCategory.SOCIAL,
    SceneType.CAFE:            SceneCategory.SOCIAL,
    SceneType.CLUB:            SceneCategory.SOCIAL,
    SceneType.PARK:            SceneCategory.SOCIAL,
    SceneType.POOL:            SceneCategory.SOCIAL,
    SceneType.BEACH:           SceneCategory.SOCIAL,
    SceneType.PARTY_VENUE:     SceneCategory.SOCIAL,
    # Private
    SceneType.APARTMENT:       SceneCategory.PRIVATE,
    SceneType.HOUSE:           SceneCategory.PRIVATE,
    SceneType.MANSION:         SceneCategory.PRIVATE,
    SceneType.COMPOUND:        SceneCategory.PRIVATE,
    SceneType.HOTEL_ROOM:      SceneCategory.PRIVATE,
    # Transit
    SceneType.BUS:             SceneCategory.TRANSIT,
    SceneType.PLANE:           SceneCategory.TRANSIT,
    SceneType.CAR:             SceneCategory.TRANSIT,
    SceneType.STATION:         SceneCategory.TRANSIT,
    SceneType.AIRPORT:         SceneCategory.TRANSIT,
    # Media
    SceneType.PRESS_ROOM:      SceneCategory.MEDIA,
    SceneType.STUDIO:          SceneCategory.MEDIA,
    SceneType.PHOTO_SHOOT:     SceneCategory.MEDIA,
    # Institutional
    SceneType.OFFICE:          SceneCategory.INSTITUTIONAL,
    SceneType.BOARDROOM:       SceneCategory.INSTITUTIONAL,
    SceneType.HOSPITAL:        SceneCategory.INSTITUTIONAL,
    SceneType.COURTROOM:       SceneCategory.INSTITUTIONAL,
}


def category_for_scene_type(scene_type: SceneType) -> SceneCategory:
    return SCENE_CATEGORY[scene_type]


# ===========================================================================
# Styled scene instances (addendum §4.1)
# ===========================================================================


class SceneInstance(str, Enum):
    """Styled variants of a ``SceneType``. Pattern: TYPE_MODIFIER."""

    APARTMENT_SHARED = "apartment_shared"
    APARTMENT_SOLO = "apartment_solo"
    APARTMENT_UPSCALE = "apartment_upscale"
    HOUSE_FAMILY = "house_family"
    HOUSE_RENTED = "house_rented"
    MANSION_OWN = "mansion_own"
    MANSION_EVENT = "mansion_event"
    BAR_LOCAL = "bar_local"
    BAR_UPSCALE = "bar_upscale"
    RESTAURANT_CASUAL = "restaurant_casual"
    RESTAURANT_FORMAL = "restaurant_formal"
    HOTEL_AWAY = "hotel_away"
    HOTEL_LAYOVER = "hotel_layover"


# Authored mapping from instance → its parent scene type. Encoded as a
# table rather than parsed from the enum value so adding instances
# can't silently drift from their parent type.
SCENE_INSTANCE_TYPE: dict[SceneInstance, SceneType] = {
    SceneInstance.APARTMENT_SHARED:  SceneType.APARTMENT,
    SceneInstance.APARTMENT_SOLO:    SceneType.APARTMENT,
    SceneInstance.APARTMENT_UPSCALE: SceneType.APARTMENT,
    SceneInstance.HOUSE_FAMILY:      SceneType.HOUSE,
    SceneInstance.HOUSE_RENTED:      SceneType.HOUSE,
    SceneInstance.MANSION_OWN:       SceneType.MANSION,
    SceneInstance.MANSION_EVENT:     SceneType.MANSION,
    SceneInstance.BAR_LOCAL:         SceneType.BAR,
    SceneInstance.BAR_UPSCALE:       SceneType.BAR,
    SceneInstance.RESTAURANT_CASUAL: SceneType.RESTAURANT,
    SceneInstance.RESTAURANT_FORMAL: SceneType.RESTAURANT,
    SceneInstance.HOTEL_AWAY:        SceneType.HOTEL_ROOM,
    SceneInstance.HOTEL_LAYOVER:     SceneType.HOTEL_ROOM,
}


def scene_type_for_instance(instance: SceneInstance) -> SceneType:
    return SCENE_INSTANCE_TYPE[instance]


def instances_of(scene_type: SceneType) -> list[SceneInstance]:
    """Inverse lookup — every authored instance for the given type.
    Returns an empty list when the type has no styled variants yet.
    """
    return [
        inst for inst, t in SCENE_INSTANCE_TYPE.items() if t == scene_type
    ]


# ===========================================================================
# Scene adjacency graph (addendum §4.2)
# ===========================================================================


# Directed edges per the addendum table. ``neighbors(t)`` reads both
# directions so authors don't have to mirror entries by hand.
_SCENE_ADJACENCY_RAW: dict[SceneType, list[SceneType]] = {
    SceneType.LOCKER_ROOM:     [SceneType.TUNNEL, SceneType.MEDICAL, SceneType.GYM],
    SceneType.TUNNEL:          [SceneType.PITCH, SceneType.STANDS, SceneType.LOCKER_ROOM],
    SceneType.GYM:             [SceneType.LOCKER_ROOM, SceneType.MEDICAL],
    SceneType.TRAINING_GROUND: [SceneType.GYM, SceneType.LOCKER_ROOM],
    SceneType.BAR:             [SceneType.RESTAURANT, SceneType.CLUB, SceneType.HOTEL_ROOM],
    SceneType.RESTAURANT:      [SceneType.BAR, SceneType.CAFE],
    SceneType.HOTEL_ROOM:      [SceneType.BAR, SceneType.POOL, SceneType.AIRPORT],
    SceneType.POOL:            [SceneType.HOTEL_ROOM, SceneType.BAR],
    SceneType.AIRPORT:         [SceneType.PLANE, SceneType.STATION],
    SceneType.PLANE:           [SceneType.AIRPORT],
    SceneType.BUS:             [SceneType.TRAINING_GROUND, SceneType.PITCH],
}


# Public, undirected view. Built once at module import so callers can
# read it without paying the symmetric-merge cost on every call.
SCENE_ADJACENCY: dict[SceneType, frozenset[SceneType]] = {}


def _build_adjacency() -> None:
    raw: dict[SceneType, set[SceneType]] = {}
    for src, dsts in _SCENE_ADJACENCY_RAW.items():
        raw.setdefault(src, set()).update(dsts)
        for dst in dsts:
            raw.setdefault(dst, set()).add(src)
    SCENE_ADJACENCY.clear()
    for k, v in raw.items():
        SCENE_ADJACENCY[k] = frozenset(v)


_build_adjacency()


def neighbors(scene_type: SceneType) -> frozenset[SceneType]:
    """Undirected neighbours of ``scene_type`` in the global scene
    adjacency graph. Returns an empty frozenset for isolated types
    (e.g. PRESS_ROOM, COURTROOM until authored)."""
    return SCENE_ADJACENCY.get(scene_type, frozenset())


# ===========================================================================
# Bridge from LocationKind (background pipeline)
# ===========================================================================


# Best-effort mapping of the visual pipeline's ``LocationKind`` to the
# narrative pipeline's ``SceneType``. Not 1:1 — ``LocationKind`` is a
# coarser visual taxonomy. SCHOOL has no direct ``SceneType`` so it
# routes through OFFICE; NEIGHBORHOOD routes through PARK as its
# closest outdoor analogue.
_LOCATION_KIND_TO_SCENE_TYPE: dict[LocationKind, SceneType] = {
    LocationKind.SUBURBAN_HOUSE: SceneType.HOUSE,
    LocationKind.APARTMENT:      SceneType.APARTMENT,
    LocationKind.SCHOOL:         SceneType.OFFICE,
    LocationKind.GYM:            SceneType.GYM,
    LocationKind.LOCKER_ROOM:    SceneType.LOCKER_ROOM,
    LocationKind.NEIGHBORHOOD:   SceneType.PARK,
    LocationKind.CAFE:           SceneType.CAFE,
    LocationKind.PARK:           SceneType.PARK,
    LocationKind.STADIUM:        SceneType.PITCH,
}


def scene_type_for_location_kind(kind: LocationKind) -> SceneType | None:
    """Bridge from the visual pipeline's ``LocationKind`` to the
    narrative ``SceneType``. Returns ``None`` for unmapped kinds so
    callers can decide whether to default or skip."""
    return _LOCATION_KIND_TO_SCENE_TYPE.get(kind)


# Reverse bridge — used by the background pipeline when an event
# blueprint authored against a SceneType needs to resolve a visual
# LocationKind for image generation.
_SCENE_TYPE_TO_LOCATION_KIND: dict[SceneType, LocationKind] = {
    SceneType.HOUSE:           LocationKind.SUBURBAN_HOUSE,
    SceneType.APARTMENT:       LocationKind.APARTMENT,
    SceneType.MANSION:         LocationKind.SUBURBAN_HOUSE,
    SceneType.COMPOUND:        LocationKind.SUBURBAN_HOUSE,
    SceneType.HOTEL_ROOM:      LocationKind.APARTMENT,
    SceneType.GYM:             LocationKind.GYM,
    SceneType.LOCKER_ROOM:     LocationKind.LOCKER_ROOM,
    SceneType.PITCH:           LocationKind.STADIUM,
    SceneType.STANDS:          LocationKind.STADIUM,
    SceneType.TUNNEL:          LocationKind.STADIUM,
    SceneType.TRAINING_GROUND: LocationKind.GYM,
    SceneType.MEDICAL:         LocationKind.SCHOOL,
    SceneType.CAFE:            LocationKind.CAFE,
    SceneType.RESTAURANT:      LocationKind.CAFE,
    SceneType.BAR:             LocationKind.CAFE,
    SceneType.CLUB:            LocationKind.CAFE,
    SceneType.PARK:            LocationKind.PARK,
    SceneType.POOL:             LocationKind.PARK,
    SceneType.BEACH:           LocationKind.PARK,
    SceneType.PARTY_VENUE:     LocationKind.CAFE,
    SceneType.OFFICE:          LocationKind.SCHOOL,
    SceneType.BOARDROOM:       LocationKind.SCHOOL,
    SceneType.HOSPITAL:        LocationKind.SCHOOL,
    SceneType.COURTROOM:       LocationKind.SCHOOL,
    SceneType.PRESS_ROOM:      LocationKind.SCHOOL,
    SceneType.STUDIO:          LocationKind.SCHOOL,
    SceneType.PHOTO_SHOOT:     LocationKind.SCHOOL,
    # Transit types have no current LocationKind — not yet wired into
    # the background pipeline.
}


def location_kind_for_scene_type(scene_type: SceneType) -> LocationKind | None:
    """Bridge from narrative ``SceneType`` → visual ``LocationKind``.
    Returns ``None`` for transit types (no LocationKind yet)."""
    return _SCENE_TYPE_TO_LOCATION_KIND.get(scene_type)
