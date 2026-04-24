"""Game session — the single facade Ren'Py talks to (technical §7.2).

Ren'Py imports the engine once and stores a ``GameSession`` on a global.
All ``.rpy`` labels call methods on this object. No simulation logic,
stat math, or event selection may live in ``.rpy`` files.

Ren'Py's save system calls ``session.serialise()`` / ``GameSession.deserialise()``.
"""

from __future__ import annotations

import random as _random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .arcs import ArcGraph, build_arc_graph, find_prior_arc_outcome
from .characters import (
    Character,
    CharacterRole,
    TierACharacter,
    TierBCharacter,
    TierDSeed,
)
from .clocks import Clock, check_triggers, force_insert_triggered, tick_clocks
from .content_loader import load_blueprints_from_path, load_templates_from_path
from .events import (
    BranchOutcome,
    EventBlueprint,
    EventInstance,
    GameContext,
    GameState,
    cast_event,
    resolve_outcome,
    select_event,
)
from .motivators import Motivator
from .narrative import (
    NarrativeTemplate,
    build_narration_context,
    narrate,
    templates_for_event,
)
from .outcomes import OutcomeRecord, WeekPhase
from .relationships import RelationshipState
from .comfyui import ComfyUIClient, comfyui_config_from_dict, comfyui_config_to_dict
from .llm import LLMClient, llm_config_from_dict, llm_config_to_dict, should_enhance
from .save import deserialise, serialise
from .schedule import BlockType, EventSlot, WeekSchedule, generate_week
from .simulation import PhaseResult, Sport, self_evaluate, simulate_phase, team_morale_delta
from .stats import StatName, StatTuple
from .visual import VisualManager


# --- Tag routing: which blueprint tags go in which block type ----------------

BLOCK_TAGS: dict[BlockType, set[str]] = {
    BlockType.DRAMA: {"conflict", "vulnerability"},
    BlockType.TRAINING: {"training"},
    BlockType.PREGAME: {"pregame"},
    BlockType.POSTGAME: {"postgame", "conflict", "vulnerability"},
    BlockType.DOWNTIME: {"downtime"},
    BlockType.GAME_PHASE: set(),  # game phases use simulation, not events
}


@dataclass
class GameSession:
    """The single object Ren'Py holds. Encapsulates all engine state."""

    state: GameState
    schedule: WeekSchedule | None
    arc_graph: ArcGraph
    blueprints: list[EventBlueprint]
    templates: list[NarrativeTemplate]
    rng: _random.Random
    np_rng: np.random.Generator
    sport: Sport = Sport.SOCCER

    # Visual manager — handles rendering and caching.
    visual_manager: VisualManager = field(default_factory=VisualManager)

    # ComfyUI image generation — enabled by default, auto-disables on errors.
    comfyui_client: ComfyUIClient = field(default_factory=ComfyUIClient)

    # LLM narration enhancer — enabled by default, auto-disables on errors.
    llm_client: LLMClient = field(default_factory=LLMClient)
    use_llm: bool = True

    # Transient match state (not saved — rebuilt each game block).
    momentum: float = 0.0
    team_morale: float = 0.0
    match_results: list[PhaseResult] = field(default_factory=list)
    opponent: list[TierDSeed] = field(default_factory=list)
    team_goals: int = 0
    opp_goals: int = 0

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def new_game(
        cls,
        player_name: str,
        *,
        roster: dict[str, TierBCharacter] | None = None,
        seed: int | None = None,
        content_root: Path | None = None,
    ) -> "GameSession":
        """Bootstrap a fresh game."""
        rng = _random.Random(seed)
        np_rng = np.random.default_rng(seed)

        root = content_root or Path(__file__).parent.parent / "content"
        blueprints = load_blueprints_from_path(root / "events")
        templates = load_templates_from_path(root / "templates")
        arc_graph = build_arc_graph(blueprints)

        player = TierACharacter(
            id="player",
            name=player_name,
            role=CharacterRole.STRIKER,
            stats={sn: StatTuple(value=0.5) for sn in StatName},
        )

        characters: dict[str, Character] = {"player": player}
        if roster:
            characters.update(roster)

        state = GameState(
            characters=characters,
            week_phase=WeekPhase(season=1, week=1),
        )

        session = cls(
            state=state,
            schedule=None,
            arc_graph=arc_graph,
            blueprints=blueprints,
            templates=templates,
            rng=rng,
            np_rng=np_rng,
        )
        # Wire ComfyUI into the visual manager.
        session.visual_manager.comfyui = session.comfyui_client
        # Warm up visuals for the starting roster.
        session.visual_manager.warm_up(characters)
        return session

    # ------------------------------------------------------------------
    # Save / load  (Ren'Py hooks)
    # ------------------------------------------------------------------

    def serialise(self) -> dict[str, Any]:
        """Produce a JSON-serialisable dict of the entire game state."""
        data = serialise(self.state, self.schedule, self.arc_graph)
        data["team_morale"] = self.team_morale
        data["momentum"] = self.momentum
        data["llm_config"] = llm_config_to_dict(self.llm_client)
        data["use_llm"] = self.use_llm
        data["comfyui_config"] = comfyui_config_to_dict(self.comfyui_client)
        return data

    @classmethod
    def deserialise(
        cls,
        data: Mapping[str, Any],
        *,
        content_root: Path | None = None,
    ) -> "GameSession":
        """Reconstruct a session from a serialised dict."""
        state, schedule, arc_graph = deserialise(data)
        root = content_root or Path(__file__).parent.parent / "content"
        blueprints = load_blueprints_from_path(root / "events")
        templates = load_templates_from_path(root / "templates")
        if arc_graph is None:
            arc_graph = build_arc_graph(blueprints)

        session = cls(
            state=state,
            schedule=schedule,
            arc_graph=arc_graph,
            blueprints=blueprints,
            templates=templates,
            rng=_random.Random(),
            np_rng=np.random.default_rng(),
        )
        session.team_morale = float(data.get("team_morale", 0.0))
        session.momentum = float(data.get("momentum", 0.0))
        if "llm_config" in data:
            session.llm_client = llm_config_from_dict(data["llm_config"])
        session.use_llm = bool(data.get("use_llm", False))
        if "comfyui_config" in data:
            session.comfyui_client = comfyui_config_from_dict(data["comfyui_config"])
        # Wire ComfyUI into the visual manager.
        session.visual_manager.comfyui = session.comfyui_client
        # Warm up visuals for loaded roster.
        session.visual_manager.warm_up(state.characters)
        return session

    # ------------------------------------------------------------------
    # Week lifecycle
    # ------------------------------------------------------------------

    def start_week(self) -> WeekSchedule:
        """Generate the schedule skeleton for the current week.

        Processes triggered clocks and force-inserts their events.
        Returns the schedule for Ren'Py to display.
        """
        wp = self.state.week_phase
        self.schedule = generate_week(wp.season, wp.week)

        # Let triggered clocks force events into the schedule.
        triggered = check_triggers(self.state.clocks)
        if triggered:
            force_insert_triggered(triggered, self.schedule)

        return self.schedule

    def advance_week(self) -> None:
        """Move to the next week (call after a week is complete)."""
        wp = self.state.week_phase
        self.state.week_phase = WeekPhase(wp.season, wp.week + 1)
        self.schedule = None
        self.match_results.clear()
        self.team_goals = 0
        self.opp_goals = 0

    # ------------------------------------------------------------------
    # Event selection & resolution
    # ------------------------------------------------------------------

    def blueprints_for_block(self, block_type: BlockType) -> list[EventBlueprint]:
        """Return blueprints whose tags overlap the block's expected set."""
        allowed = BLOCK_TAGS.get(block_type, set())
        if not allowed:
            return []
        return [bp for bp in self.blueprints if bp.tags & allowed]

    def select_event_for_slot(self, slot_index: int) -> EventBlueprint | None:
        """Pick an event for the given schedule slot.

        If the slot has a ``forced_event_id``, that blueprint is returned
        directly. Otherwise the selection pipeline runs.
        """
        if self.schedule is None:
            return None
        slot = self.schedule.slots[slot_index]

        if slot.forced_event_id is not None:
            for bp in self.blueprints:
                if bp.id == slot.forced_event_id:
                    return bp
            return None

        candidates = self.blueprints_for_block(slot.block_type)
        ctx = self._game_context()
        return select_event(candidates, ctx, self.state, self.rng)

    def cast_event(self, blueprint: EventBlueprint) -> dict[str, Character] | None:
        """Attempt to cast the blueprint against the current roster."""
        return cast_event(blueprint, self.state, self.rng)

    def resolve_event(
        self,
        blueprint: EventBlueprint,
        branch: str,
        cast: dict[str, Character],
        slot_index: int,
    ) -> OutcomeRecord:
        """Apply outcome effects and record the resolution.

        Mutates ``state`` and marks the schedule slot as resolved.
        """
        prior = find_prior_arc_outcome(
            blueprint.id, self.arc_graph, self.state.outcome_log
        )
        record = resolve_outcome(blueprint, branch, cast, self.state, prior)

        if self.schedule is not None:
            slot = self.schedule.slots[slot_index]
            slot.resolved_event_id = blueprint.id
            slot.resolved_branch = branch

        return record

    def narrate_outcome(
        self,
        blueprint: EventBlueprint,
        cast: dict[str, Character],
        record: OutcomeRecord,
    ) -> str:
        """Produce a narration string for a resolved event."""
        player = cast.get("player")
        event_templates = templates_for_event(
            self.templates, blueprint.id, blueprint.tags
        )
        ctx = build_narration_context(
            target=player,
            cast=cast,
            outcome_log=self.state.outcome_log,
            trigger_outcome=record,
            team_morale=self.team_morale,
            branch_summary=record.summary,
        )
        return narrate(
            event_templates,
            ctx,
            self.rng,
            use_llm=self.use_llm,
            llm_client=self.llm_client,
            event_tags=blueprint.tags,
        )

    # ------------------------------------------------------------------
    # Match simulation
    # ------------------------------------------------------------------

    def setup_match(
        self,
        opponent: Sequence[TierDSeed] | None = None,
        *,
        opponent_rating: float = 0.5,
        opponent_count: int = 11,
    ) -> None:
        """Prepare for a match. Creates an opponent if none given."""
        if opponent is not None:
            self.opponent = list(opponent)
        else:
            self.opponent = [
                TierDSeed(
                    role=CharacterRole.MIDFIELDER,
                    skill_rating=opponent_rating,
                )
                for _ in range(opponent_count)
            ]
        self.momentum = 0.0
        self.match_results.clear()
        self.team_goals = 0
        self.opp_goals = 0

    def roster_players(self) -> list[Character]:
        """Return the playable roster (all characters in state)."""
        return list(self.state.characters.values())

    def simulate_game_phase(self, phase_index: int, total_phases: int = 8) -> PhaseResult:
        """Run one phase of the match simulation.

        Returns a ``PhaseResult`` for Ren'Py to display.
        """
        players = self.roster_players()
        result = simulate_phase(
            players,
            self.opponent,
            phase_index,
            self.momentum,
            self.np_rng,
            sport=self.sport,
            total_phases=total_phases,
        )
        self.momentum = result.momentum
        if result.goal_scored:
            self.team_goals += 1
        self.match_results.append(result)
        return result

    def evaluate_match(self) -> dict[str, Any]:
        """Post-match evaluation: self-evaluation + morale update.

        Returns a summary dict for Ren'Py to use in postgame narration.
        """
        if not self.match_results:
            return {"perceived": 0.5, "mood_delta": 0.0, "morale_delta": 0.0}

        # Average performance across phases for each player.
        players = self.roster_players()
        all_perfs = np.stack([r.performances for r in self.match_results])
        mean_perfs = all_perfs.mean(axis=0)

        # Self-evaluate the player character.
        perceived = 0.5
        mood_delta = 0.0
        player = self.state.characters.get("player")
        if isinstance(player, TierACharacter):
            player_idx = next(
                (i for i, c in enumerate(players) if c.id == "player"), 0
            )
            perceived, mood_delta = self_evaluate(
                player, float(mean_perfs[player_idx]), self.np_rng
            )

        # Team morale — pass full roster; function filters for Tier A internally.
        morale_delta = team_morale_delta(players, mean_perfs, self.np_rng)
        self.team_morale += morale_delta

        # Tick clocks based on match outcome.
        if self.team_morale < -0.2:
            tick_clocks(self.state.clocks, 0.2, reason="bad result")
        elif self.team_morale > 0.2:
            tick_clocks(self.state.clocks, 0.05, reason="good result")

        return {
            "perceived": perceived,
            "mood_delta": mood_delta,
            "morale_delta": morale_delta,
            "team_goals": self.team_goals,
            "opp_goals": self.opp_goals,
            "team_morale": self.team_morale,
        }

    # ------------------------------------------------------------------
    # Slot queries
    # ------------------------------------------------------------------

    def pending_slots(self) -> list[tuple[int, EventSlot]]:
        """Return ``(index, slot)`` pairs for unresolved slots."""
        if self.schedule is None:
            return []
        return [
            (i, s) for i, s in enumerate(self.schedule.slots)
            if s.resolved_event_id is None
        ]

    def slot_summary(self) -> list[dict[str, Any]]:
        """Build a display-friendly summary of the week's schedule."""
        if self.schedule is None:
            return []
        out: list[dict[str, Any]] = []
        for i, slot in enumerate(self.schedule.slots):
            out.append({
                "index": i,
                "block_type": slot.block_type.value,
                "phase_index": slot.phase_index,
                "forced": slot.forced_event_id,
                "resolved": slot.resolved_event_id,
                "branch": slot.resolved_branch,
            })
        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _game_context(self) -> GameContext:
        return GameContext(
            week_phase=self.state.week_phase,
            team_morale=self.team_morale,
            momentum=self.momentum,
            flags=set(),
        )

    def get_choices(self, blueprint: EventBlueprint) -> dict[str, str]:
        """Return the player-facing choices for a blueprint.

        Scans scene blocks for ChoiceNodes. Returns
        ``{choice_id: label}`` for the first choice found.
        """
        for block in blueprint.blocks:
            if block.choice is not None:
                return dict(block.choice.options)
        # No explicit choice → expose outcome branches as implicit choices.
        return {branch: branch.replace("_", " ").title() for branch in blueprint.outcomes}
