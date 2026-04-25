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
from .background_generator import (
    BackgroundGenerator,
    DeferredPrefetchScheduler,
    PlaceholderImageProducer,
)
from .background_pool import (
    BackgroundManifest,
    LocationDescriptor,
    LocationKind,
    SceneGraphSpec,
)
from .clock import Slot, SLOT_START_HOUR, Weekday, WorldClock
from .color_grades import (
    SceneAtmosphere,
    SceneMood,
    TimeOfDay,
    Weather,
    derive_mood,
    draw_weather,
    draw_weather_tendency,
    generate_grade_pngs,
    grade_path,
    time_of_day_for_hour,
)
from .characters import (
    Character,
    CharacterRole,
    TierACharacter,
    TierBCharacter,
    TierDSeed,
)
from .clocks import Clock, check_triggers, force_insert_triggered, tick_clocks
from .content_loader import (
    load_blueprints_from_path,
    load_scene_specs_from_path,
    load_templates_from_path,
)
from .events import (
    BranchOutcome,
    EventBlueprint,
    EventInstance,
    GameContext,
    GameState,
    LocationCue,
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

def _load_scene_specs_safe(scenes_root: Path) -> list[SceneGraphSpec]:
    """Load authored scene graph specs; return empty list if dir missing.

    The background pipeline is optional — tests and content roots without
    a ``scenes/`` directory should still bootstrap a session.
    """
    if not scenes_root.exists():
        return []
    return load_scene_specs_from_path(scenes_root)


@dataclass(frozen=True)
class ClockDisplay:
    """Status-bar snapshot read by Ren'Py overlays.

    A frozen capture of the world clock plus a couple of derived
    fields used by the status bar (``transition_warning`` for the
    "slot ending soon" cue, ``match_label`` for the in-match override).
    """

    week: int
    weekday: Weekday
    slot: Slot
    hour_minute: str
    next_slot_in_minutes: int
    transition_warning: bool
    match_label: str | None = None


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

    # Background pipeline — wired in by ``new_game`` / ``deserialise``.
    # ``background_generator`` is None when no scene specs are loaded; the
    # session degrades gracefully (events with location cues simply skip
    # the background lookup).
    scene_specs: dict[str, SceneGraphSpec] = field(default_factory=dict)
    background_manifest: BackgroundManifest | None = None
    background_generator: BackgroundGenerator | None = None
    grades_root: Path | None = None  # set by ``init_backgrounds``

    # During match play the status bar swaps from the clock to a label
    # (e.g. "Match vs Northgate"). Set by the match flow (Phase 11.5B);
    # cleared after the match block ends.
    _active_match_label: str | None = None
    # Default location descriptor per spec_id, used when an ad-hoc
    # ``LocationCue`` doesn't carry overrides. Authors may also call
    # ``session.set_default_descriptor`` at game-setup time.
    default_location_descriptors: dict[str, LocationDescriptor] = field(
        default_factory=dict
    )

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
        scene_specs = _load_scene_specs_safe(root / "scenes")
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
            scene_specs={s.spec_id: s for s in scene_specs},
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
        scene_specs = _load_scene_specs_safe(root / "scenes")
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
            scene_specs={s.spec_id: s for s in scene_specs},
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
        Draws the week's ``weather_tendency`` and per-slot weathers
        (game-phase slots all share one match weather). Returns the
        schedule for Ren'Py to display.
        """
        wp = self.state.week_phase
        self.schedule = generate_week(wp.season, wp.week)

        # Reset the world clock to Monday 08:00 of this week. Day-by-day
        # advancement will arrive in 11.5B; for now ``start_week``
        # establishes the canonical week-start time.
        self.state.clock = WorldClock(
            week=wp.week, weekday=Weekday.MON, hour=8, minute=0,
        )

        # Let triggered clocks force events into the schedule.
        triggered = check_triggers(self.state.clocks)
        if triggered:
            force_insert_triggered(triggered, self.schedule)

        # Draw weather. Tendency once per week; per-day variation
        # biased toward it. All slots on a given weekday share that
        # day's draw — including all eight match phases on Saturday.
        tendency = draw_weather_tendency(self.rng)
        self.schedule.weather_tendency = tendency.value
        daily: dict[str, str] = {}
        for slot in self.schedule.slots:
            if slot.weekday is None:
                continue
            key = slot.weekday.value
            if key not in daily:
                daily[key] = draw_weather(tendency, self.rng).value
        self.schedule.daily_weathers = daily

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
        """Apply outcome effects, record the resolution, and advance time.

        Mutates ``state`` and marks the schedule slot as resolved. The
        world clock advances by the resolved branch's duration (or the
        blueprint default when the branch doesn't override). Game-phase
        slots are skipped — the match block consumes its time as a
        single advance handled by ``evaluate_match``.
        """
        prior = find_prior_arc_outcome(
            blueprint.id, self.arc_graph, self.state.outcome_log
        )
        record = resolve_outcome(blueprint, branch, cast, self.state, prior)

        if self.schedule is not None:
            slot = self.schedule.slots[slot_index]
            slot.resolved_event_id = blueprint.id
            slot.resolved_branch = branch
            if slot.block_type != BlockType.GAME_PHASE:
                self._advance_clock_for_event(blueprint, branch)

        return record

    def _advance_clock_for_event(
        self, blueprint: EventBlueprint, branch: str
    ) -> int:
        """Advance the clock for one resolved event. Returns the minutes
        advanced. Branch-level ``duration_minutes`` overrides the
        blueprint default; both fall back to 60.
        """
        outcome = blueprint.outcomes.get(branch)
        minutes = (
            outcome.duration_minutes
            if outcome is not None and outcome.duration_minutes is not None
            else blueprint.duration_minutes
        )
        self.state.clock.advance(minutes)
        return minutes

    def enter_slot(self, slot_index: int) -> int:
        """Fast-forward the world clock to the start of a schedule slot.

        Ren'Py calls this before playing each anchored slot — when the
        Friday afternoon pregame starts, the clock should already read
        Fri 16:00 regardless of where Wed/Thu's events left it. Returns
        the number of minutes advanced (0 when already at or past the
        anchor on the right day).

        Slots without a calendar tag are no-ops, so older flat-list
        schedules continue to work without time advance.
        """
        if self.schedule is None:
            return 0
        if not 0 <= slot_index < len(self.schedule.slots):
            return 0
        slot = self.schedule.slots[slot_index]
        if slot.weekday is None or slot.slot is None:
            return 0
        clock = self.state.clock
        target_hour = SLOT_START_HOUR[slot.slot]
        # Compute days between current weekday and the slot's weekday.
        order = list(Weekday)
        cur_idx = order.index(clock.weekday)
        tgt_idx = order.index(slot.weekday)
        day_delta = tgt_idx - cur_idx
        if day_delta < 0:
            day_delta += 7  # next week's same weekday
        target_minutes = day_delta * 24 * 60 + target_hour * 60
        current_minutes = clock.total_minutes_in_day()
        if day_delta == 0 and target_minutes <= current_minutes:
            return 0
        delta = target_minutes - current_minutes
        if delta <= 0:
            delta += 7 * 24 * 60
        clock.advance(delta)
        return delta

    # ------------------------------------------------------------------
    # Background scene lookup
    # ------------------------------------------------------------------

    def init_backgrounds(
        self,
        assets_root: Path,
        *,
        producer=None,
        prefetch_scheduler=None,
        warm_marquees: bool = False,
    ) -> None:
        """Wire the background manifest + generator at game-setup time.

        Ren'Py calls this once during boot with the project's assets dir.
        Tests pass a tmp_path so generated placeholders don't pollute the
        repo. Idempotent — re-running rebuilds against the on-disk
        manifest, useful after a save load.

        ``producer`` defaults to ``PlaceholderImageProducer`` (solid colours)
        until the SD pipeline is wired in. ``prefetch_scheduler`` defaults
        to ``DeferredPrefetchScheduler`` so prefetch jobs queue up and
        ``drain_background_prefetch`` runs them on idle ticks.

        When ``warm_marquees`` is True, every blueprint with a marquee
        ``LocationCue`` (one carrying a stable ``graph_id``) gets its
        graph created eagerly and a full 3-variant generation scheduled
        for the cue's entry node — used at game start for known
        locations like ``player_home`` and ``main_school``.
        """
        if not self.scene_specs:
            self.background_manifest = None
            self.background_generator = None
            self.grades_root = None
            return
        assets_root = Path(assets_root)
        manifest = BackgroundManifest.load(assets_root)
        self.background_manifest = manifest
        self.background_generator = BackgroundGenerator(
            manifest=manifest,
            specs=self.scene_specs,
            producer=producer or PlaceholderImageProducer(),
            prefetch_scheduler=prefetch_scheduler or DeferredPrefetchScheduler(),
        )
        # Render the colour-grade PNGs into ``<assets_root>/../grades/``
        # so they live alongside other generated visual assets. Hash-keyed
        # cache means this is essentially free on subsequent boots.
        self.grades_root = assets_root.parent / "grades"
        generate_grade_pngs(self.grades_root)
        if warm_marquees:
            self.warm_marquees()

    def set_default_descriptor(
        self, spec_id: str, descriptor: LocationDescriptor
    ) -> None:
        """Authored hook: tell the session what an ad-hoc graph of `spec_id`
        should look like by default. Overrides on a `LocationCue` are
        merged on top.
        """
        if spec_id not in self.scene_specs:
            raise KeyError(f"unknown spec_id: {spec_id!r}")
        self.default_location_descriptors[spec_id] = descriptor

    def resolve_scene(
        self,
        blueprint: EventBlueprint,
        cast: dict[str, Character],
    ) -> tuple[str, str] | None:
        """Determine `(graph_id, node_name)` for an event's background.

        Returns ``None`` if the blueprint has no location cue or if the
        background pipeline isn't initialised. Marquee cues return their
        fixed `graph_id`. Ad-hoc cues create a fresh graph (closed after
        ``release_scene``).
        """
        cue = blueprint.location
        if cue is None or self.background_manifest is None:
            return None
        if cue.spec_id not in self.scene_specs:
            return None

        if cue.graph_id is not None:
            # Marquee — create the graph on first use.
            if self.background_manifest.get_graph(cue.graph_id) is None:
                descriptor = self._descriptor_for(cue)
                self.background_manifest.create_graph(
                    cue.spec_id, descriptor, graph_id=cue.graph_id
                )
            return cue.graph_id, cue.node_name

        # Ad-hoc — fresh graph each call.
        descriptor = self._descriptor_for(cue)
        graph = self.background_manifest.create_graph(cue.spec_id, descriptor)
        return graph.graph_id, cue.node_name

    def scene_path(self, graph_id: str, node_name: str) -> Path | None:
        """Return the absolute image path for a graph node, generating
        synchronously if needed. Returns ``None`` if the pipeline is off.

        This is the *primary* image. Use ``scene_variants`` for the full
        list (primary + subtle-motion variants) when driving an ATL
        crossfade.
        """
        if self.background_generator is None:
            return None
        return self.background_generator.get_background(graph_id, node_name)

    def scene_variants(
        self, graph_id: str, node_name: str
    ) -> list[Path]:
        """Return all variants attached to a node — primary at index 0,
        subtle-motion variants after.

        Returns an empty list if the pipeline is off or the node hasn't
        been visited. Does not generate, mark visited, or schedule —
        call ``scene_path`` first to ensure the primary exists.
        """
        if self.background_generator is None:
            return []
        return self.background_generator.get_variants(graph_id, node_name)

    def warm_marquees(self) -> int:
        """Schedule eager generation for every marquee location declared
        by an authored blueprint.

        Walks ``self.blueprints`` for ``LocationCue``s carrying a stable
        ``graph_id``. For each unique marquee, ensures the graph exists
        and schedules the entry node's primary plus 2 motion variants.
        Returns the number of marquees newly warmed (idempotent — running
        again is a no-op for already-warmed graphs).
        """
        if self.background_generator is None or self.background_manifest is None:
            return 0
        warmed = 0
        seen: set[str] = set()
        for bp in self.blueprints:
            cue = bp.location
            if cue is None or cue.graph_id is None:
                continue
            if cue.graph_id in seen:
                continue
            seen.add(cue.graph_id)
            if cue.spec_id not in self.scene_specs:
                continue
            if self.background_manifest.get_graph(cue.graph_id) is None:
                descriptor = self._descriptor_for(cue)
                self.background_manifest.create_graph(
                    cue.spec_id, descriptor, graph_id=cue.graph_id
                )
            self.background_generator.warm_node(cue.graph_id, cue.node_name)
            warmed += 1
        return warmed

    def release_scene(self, graph_id: str, *, close: bool = False) -> None:
        """Reap unvisited prefetches for `graph_id`. Closes the graph when
        `close=True` (use this for ad-hoc graphs after their event ends)."""
        if self.background_manifest is None:
            return
        self.background_manifest.reap_unvisited(graph_id)
        if close:
            self.background_manifest.close_graph(graph_id)
        self.background_manifest.save()

    def atmosphere(self) -> SceneAtmosphere:
        """Project current state onto a ``SceneAtmosphere``.

        - ``time_of_day`` derives from ``state.clock.hour`` via the
          colour-grade band table — same hour reads the same way
          regardless of which block is being played.
        - ``weather`` is the day's draw recorded at ``start_week``,
          looked up by ``state.clock.weekday``. Falls back to the
          week's tendency when the day has no draw, then to ``CLEAR``
          when no schedule is active.
        - ``mood`` derives from current ``team_morale`` and ``momentum``
          via :func:`derive_mood`.
        """
        clock = self.state.clock
        time_of_day = time_of_day_for_hour(clock.hour)
        weather = Weather.CLEAR
        tendency = Weather.CLEAR
        if self.schedule is not None:
            if self.schedule.weather_tendency is not None:
                tendency = Weather(self.schedule.weather_tendency)
                weather = tendency
            day_value = self.schedule.weather_for(clock.weekday)
            if day_value is not None:
                weather = Weather(day_value)
        mood = derive_mood(self.team_morale, self.momentum)
        return SceneAtmosphere(
            time_of_day=time_of_day,
            weather=weather,
            mood=mood,
            weather_tendency=tendency,
        )

    def grade_paths(self) -> tuple[Path, Path, Path] | None:
        """Return absolute PNG paths for the three grade layers in the
        order ``(time_of_day, weather, mood)``.

        Returns ``None`` if the background pipeline isn't initialised
        (no grades dir resolved). Paths always exist on disk because
        ``init_backgrounds`` regenerates them from the lookup tables.
        """
        if self.grades_root is None:
            return None
        atm = self.atmosphere()
        return (
            grade_path(self.grades_root, "time", atm.time_of_day.value),
            grade_path(self.grades_root, "weather", atm.weather.value),
            grade_path(self.grades_root, "mood", atm.mood.value),
        )

    def clock_display(self) -> "ClockDisplay":
        """Status-bar surface read by Ren'Py overlays.

        Includes the upcoming-slot warning so the UI can show a small
        cue ("Afternoon ending") under the time when the next event
        would push the clock across a slot boundary. Returns a frozen
        snapshot — Ren'Py can cache it between events without worrying
        about aliasing.
        """
        clock = self.state.clock
        slot = clock.current_slot()
        next_slot_minutes = clock.minutes_until_next_slot()
        return ClockDisplay(
            week=clock.week,
            weekday=clock.weekday,
            slot=slot,
            hour_minute=clock.hour_minute(),
            next_slot_in_minutes=next_slot_minutes,
            transition_warning=next_slot_minutes <= 30,
            match_label=self._active_match_label,
        )

    def drain_background_prefetch(self, max_items: int | None = None) -> int:
        """Run pending prefetch jobs. Ren'Py calls this on idle ticks so
        the player never blocks on background generation."""
        if self.background_generator is None:
            return 0
        scheduler = self.background_generator.prefetch_scheduler
        drain = getattr(scheduler, "drain", None)
        if drain is None:
            return 0
        return drain(max_items)

    def _descriptor_for(self, cue: LocationCue) -> LocationDescriptor:
        base = self.default_location_descriptors.get(cue.spec_id)
        if base is None:
            spec = self.scene_specs[cue.spec_id]
            base = LocationDescriptor(kind=spec.kind)
        if not cue.descriptor_overrides:
            return base
        merged = base.to_dict()
        merged.update(cue.descriptor_overrides)
        return LocationDescriptor.from_dict(merged)

    def narrate_outcome(
        self,
        blueprint: EventBlueprint,
        cast: dict[str, Character],
        record: OutcomeRecord,
    ) -> list[str]:
        """Produce paginated narration for a resolved event.

        Returns a list of screen-sized pages. Short narration yields a
        single-page list; long template fills or LLM rephrasings split
        on sentence boundaries. Callers iterate the list to display each
        page in turn.
        """
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
        opponent_name: str = "Opponent",
    ) -> None:
        """Prepare for a match. Creates an opponent if none given.

        ``opponent_name`` is shown on the status bar in place of the
        clock for the duration of the match block ("Match vs Northgate"
        rather than the literal time). The label clears when
        ``evaluate_match`` runs.
        """
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
        # Status bar swap: covers the four-hour afternoon block.
        self._active_match_label = f"Match vs {opponent_name}"

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
            # Even on the empty path, the match block has been "spent":
            # clear the status label and snap to evening so the schedule
            # progresses normally.
            self._active_match_label = None
            self.state.clock.fast_forward_to_slot(Slot.EVENING)
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

        # Match block ends: clear the status-bar label and fast-forward
        # the clock to evening (20:00). The afternoon block's four hours
        # are consumed regardless of how many phases ran or how long the
        # in-fiction match was.
        self._active_match_label = None
        self.state.clock.fast_forward_to_slot(Slot.EVENING)

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
