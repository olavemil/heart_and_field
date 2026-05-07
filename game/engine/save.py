"""Save / load — full state serialisation (technical §8).

``serialise`` converts the entire game state into a plain dict tree
(JSON-compatible). ``deserialise`` reconstructs it. Every engine
dataclass already has ``to_dict`` / ``from_dict``; this module
orchestrates the top-level envelope.

Ren'Py's save system will call ``serialise`` / ``deserialise`` on the
single ``engine`` object. Nothing in this module may import ``renpy``.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from .arcs import ArcGraph
from .characters import Character, TierACharacter, TierBCharacter
from .clock import WorldClock
from .clocks import Clock
from .events import GameState, _default_clock
from .outcomes import OutcomeRecord, WeekPhase
from .placeholders import CharacterPlaceholder
from .schedule import WeekSchedule
from .secrets import Secret


# --- Serialise ---------------------------------------------------------------


def serialise(
    state: GameState,
    schedule: WeekSchedule | None = None,
    arc_graph: ArcGraph | None = None,
) -> dict[str, Any]:
    """Convert all game state into a JSON-serialisable dict.

    Parameters:
        state: the mutable world (characters, outcomes, clocks, etc.).
        schedule: the current week schedule (may be None between weeks).
        arc_graph: the arc dependency graph (optional; can be rebuilt from
                   blueprints, but saving it avoids recomputation).

    Returns:
        A nested dict that ``json.dumps`` can handle directly.
    """
    current_location = (
        list(state.current_location)
        if state.current_location is not None
        else None
    )
    return {
        "version": 1,
        "week_phase": state.week_phase.to_dict(),
        "world_clock": state.clock.to_dict(),
        "current_location": current_location,
        "characters": {
            cid: _serialise_character(c)
            for cid, c in state.characters.items()
        },
        "outcome_log": [o.to_dict() for o in state.outcome_log],
        "completed_event_ids": sorted(state.completed_event_ids),
        "disabled_event_ids": sorted(state.disabled_event_ids),
        "clocks": [c.to_dict() for c in state.clocks],
        "secrets": {sid: s.to_dict() for sid, s in state.secrets.items()},
        "placeholders": {
            pid: p.to_dict() for pid, p in state.placeholders.items()
        },
        "schedule": schedule.to_dict() if schedule is not None else None,
        "arc_graph": arc_graph.to_dict() if arc_graph is not None else None,
    }


def _serialise_character(char: Character) -> dict:
    """Dispatch to the character's own ``to_dict``."""
    return char.to_dict()


# --- Deserialise -------------------------------------------------------------


def deserialise(
    data: Mapping[str, Any],
) -> tuple[GameState, WeekSchedule | None, ArcGraph | None]:
    """Reconstruct game state from a serialised dict.

    Returns:
        (state, schedule, arc_graph) — schedule and arc_graph may be None
        if they weren't saved.
    """
    characters: dict[str, Character] = {}
    for cid, cdata in data.get("characters", {}).items():
        characters[cid] = _deserialise_character(cdata)

    clocks = [Clock.from_dict(c) for c in data.get("clocks", [])]

    clock_data = data.get("world_clock")
    world_clock = (
        WorldClock.from_dict(clock_data)
        if clock_data is not None
        else _default_clock()
    )

    loc = data.get("current_location")
    current_location = (
        (str(loc[0]), str(loc[1]))
        if loc is not None and len(loc) == 2
        else None
    )

    state = GameState(
        characters=characters,
        outcome_log=[
            OutcomeRecord.from_dict(o) for o in data.get("outcome_log", [])
        ],
        completed_event_ids=set(data.get("completed_event_ids", [])),
        disabled_event_ids=set(data.get("disabled_event_ids", [])),
        week_phase=WeekPhase.from_dict(data.get("week_phase", {"season": 1, "week": 1})),
        clocks=clocks,
        clock=world_clock,
        current_location=current_location,
        secrets={
            sid: Secret.from_dict(sdata)
            for sid, sdata in data.get("secrets", {}).items()
        },
        placeholders={
            pid: CharacterPlaceholder.from_dict(pdata)
            for pid, pdata in data.get("placeholders", {}).items()
        },
    )

    schedule = None
    if data.get("schedule") is not None:
        schedule = WeekSchedule.from_dict(data["schedule"])

    arc_graph = None
    if data.get("arc_graph") is not None:
        arc_graph = ArcGraph.from_dict(data["arc_graph"])

    return state, schedule, arc_graph


def _deserialise_character(data: Mapping) -> Character:
    """Dispatch based on the ``tier`` marker set by ``to_dict``."""
    tier = data.get("tier", "B")
    if tier == "A":
        return TierACharacter.from_dict(data)
    return TierBCharacter.from_dict(data)


# --- Convenience I/O --------------------------------------------------------


def save_to_json(
    path: str,
    state: GameState,
    schedule: WeekSchedule | None = None,
    arc_graph: ArcGraph | None = None,
) -> None:
    """Serialise and write to a JSON file."""
    data = serialise(state, schedule, arc_graph)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_from_json(
    path: str,
) -> tuple[GameState, WeekSchedule | None, ArcGraph | None]:
    """Read a JSON file and deserialise."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return deserialise(data)
