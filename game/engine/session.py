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
    NoOpPrefetchScheduler,
    PlaceholderImageProducer,
    PrebakedImageProducer,
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
from .overlays import (
    OverlaySpec,
    generate_overlay_pngs,
    overlay_path,
    overlays_for,
)
from .characters import (
    Character,
    CharacterRole,
    Disposition,
    NON_PLAYING_ROLES,
    TierACharacter,
    TierBCharacter,
    TierDSeed,
)
from .sprite_pool import GenderPresentation
from .quirks import Quirk
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
    PlayerStance,
    cast_event,
    resolve_outcome,
    select_event,
    weighted_player_stance,
)
from .event_taxonomy import EventTone
from .figures import (
    FigureCategory,
    FigureManifest,
    FigurePosture,
    appearance_from_descriptor,
    context_for_node,
    select_figure,
    select_for_character,
)
from .figure_layout import (
    FigureBox,
    FigureDistance,
    FigureSlot,
    PlayerFraming,
    compute_layout,
)
from .sprite_pool import CharacterDescriptor
from .motivators import Motivator
from .narrative import (
    NarrationContext,
    NarrativeTemplate,
    _substitute,
    build_narration_context,
    compress_arc_summary,
    narrate,
    narrate_match_phase,
    paginate,
    self_evaluation_line,
    templates_for_event,
)
from .outcomes import OutcomeRecord, WeekPhase
from .relationships import RelationshipState
from .journal import NarrativeJournal
from .llm import (
    LLMClient,
    llm_config_from_dict,
    llm_config_to_dict,
    recap_arc,
    should_enhance,
    summarise_narration,
)
from .save import deserialise, serialise
from .schedule import BlockType, EventSlot, WeekSchedule, generate_week
from .simulation import PhaseResult, Sport, self_evaluate, simulate_phase, team_morale_delta
from .stats import StatName, StatTuple
from .visual import VisualManager
from .stock_faces import StockFacePool
from .roster_factory import Roster, generate_roster, generate_season_opponents
from .league import LeagueConfig, LeagueFormat, LeagueTier, Season, TIER_SKILL_RANGES, generate_season
from .scene_taxonomy import location_kind_for_scene_type
from .world_genesis import generate_secret_web


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


@dataclass
class NarratedBeat:
    """One screen-group of an event's narration (Phase 24B).

    ``kind`` is ``"setup"`` / ``"action"`` / ``"reaction"`` / ``"result"``;
    ``pages`` are the screen-sized strings Ren'Py shows in turn. Carrying
    the beat kind (rather than a flat page list) gives the presentation
    layer a hook to re-frame between beats — e.g. re-pose figures when a
    reaction lands (Phase 24D).
    """

    kind: str
    pages: list[str] = field(default_factory=list)


@dataclass
class PlayerCustomisation:
    """Player-facing overrides for the generated character.

    Every field is optional — ``None`` means "randomise this axis".
    Passed to :meth:`GameSession.new_game` when the player wants to
    shape their character rather than accept the default.
    """

    name: str | None = None
    role: CharacterRole | None = None
    gender_presentation: GenderPresentation | None = None
    disposition: Disposition | None = None
    quirks: list[Quirk] | None = None
    stats: dict[StatName, float] | None = None


BLOCK_TAGS: dict[BlockType, set[str]] = {
    BlockType.DRAMA: {
        "conflict",
        "vulnerability",
        "social",
        "secret",
        "romantic",
        "institutional",
        "external_pressure",
        "mentor",
        "rival",
    },
    BlockType.TRAINING: {"training"},
    BlockType.PREGAME: {"pregame"},
    BlockType.POSTGAME: {"postgame", "conflict", "vulnerability", "celebration"},
    BlockType.DOWNTIME: {"downtime", "social", "solo", "romantic", "celebration"},
    BlockType.GAME_PHASE: set(),  # game phases use simulation, not events
}

# Blueprints carrying these tags resolve inside the match block, not in
# schedule slots — they fire from the phase loop via ``select_match_event``
# (Phase 22F), never from ``blueprints_for_block``.
IN_MATCH_TAGS: set[str] = {"ingame"}

# Probability that a teammate goal opens a playable in-phase beat, so not
# every goal interrupts the run of play.
MATCH_EVENT_GOAL_CHANCE: float = 0.6

# Scene-intro atmosphere lines per event tone (Phase 22D). The pools feed
# the deterministic intro; with the LLM on, this assembled line is the
# grounding the model rephrases (so even repeats read fresh).
_TONE_INTRO_LINES: dict[EventTone, tuple[str, ...]] = {
    EventTone.HOSTILE: (
        "The air has edges.",
        "Nobody is pretending this is friendly.",
        "The room has already taken sides.",
        "Something is going to be said that can't be unsaid.",
    ),
    EventTone.TENSE: (
        "Something here is being carefully not said.",
        "The room is quieter than it has any reason to be.",
        "Everyone is waiting for someone else to go first.",
        "The small talk has run out and left a gap.",
    ),
    EventTone.WARM: (
        "It's easy here, for once.",
        "The kind of company that doesn't cost anything.",
        "Nobody needs anything from anybody.",
        "There's no edge to it tonight.",
    ),
    EventTone.ROMANTIC: (
        "Neither of you is quite looking at the other.",
        "The distance between you keeps needing renegotiating.",
        "The conversation keeps finding reasons not to end.",
        "Something unspoken is doing most of the talking.",
    ),
    EventTone.PLAYFUL: (
        "Someone is already laughing.",
        "Trouble, but the friendly kind.",
        "It's loose and loud and going nowhere useful.",
        "Nobody's taking anything seriously yet.",
    ),
    EventTone.MELANCHOLY: (
        "Everything here feels a little heavier than it looks.",
        "The light feels like late afternoon, whatever the clock says.",
        "Nobody's in a hurry to be anywhere.",
        "It's the quiet that comes after, not before.",
    ),
    EventTone.TRIUMPHANT: (
        "The day still has the win in it.",
        "Everyone is walking taller than usual.",
        "The good mood hasn't worn off yet.",
        "Something went right, and it shows.",
    ),
    EventTone.NEUTRAL: (
        "Just another part of the day.",
        "Nothing about it announces itself.",
        "An ordinary hour, so far.",
    ),
}

def _recap_distance_phrase(gap_days: int) -> str:
    """Lead-in for the arc recap beat, scaled to how long the thread has
    lapsed (Phase 24C). Used as the deterministic framing and as LLM
    grounding so the callback keeps a sense of elapsed time."""
    if gap_days <= 1:
        return "The day before"
    if gap_days <= 3:
        return "A couple of days earlier"
    if gap_days <= 6:
        return "Earlier that week"
    if gap_days <= 13:
        return "The week before"
    return "Some time before"


# Player stance → figure framing (Phase 24C). An actor or reactor holds
# the foreground; an onlooker sits aside; a spectator is pushed small and
# to the edge. Bridges the authored ``EventBlueprint.player_stance`` to
# the geometry knob in ``figure_layout``.
_STANCE_TO_FRAMING: dict[PlayerStance, PlayerFraming] = {
    PlayerStance.ACTOR: PlayerFraming.FOREGROUND,
    PlayerStance.REACTOR: PlayerFraming.FOREGROUND,
    PlayerStance.ONLOOKER: PlayerFraming.ASIDE,
    PlayerStance.SPECTATOR: PlayerFraming.BACKGROUND,
}

# Player stance → a short LLM grounding note so narration reflects how
# present the viewpoint character is (Phase 24C). ACTOR is the unmarked
# default and gets no note.
_STANCE_PERSPECTIVE: dict[PlayerStance, str] = {
    PlayerStance.REACTOR: (
        "The viewpoint character is responding to this scene rather than "
        "driving it."
    ),
    PlayerStance.ONLOOKER: (
        "The viewpoint character is on the edge of this scene, half an "
        "observer."
    ),
    PlayerStance.SPECTATOR: (
        "The viewpoint character is mostly watching the others here, not "
        "acting."
    ),
}


# Role names checked, in order, when picking which cast member a scene
# puts on screen (Phase 22D sprite wiring).
_FOCAL_ROLE_PRIORITY: tuple[str, ...] = (
    "target",
    "partner",
    "rival",
    "mentor",
    "friend",
    "confidant",
    "interest",
    "accuser",
    "coach",
    "official",
)


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

    # Visual manager — handles rendering and caching. Runtime visuals are
    # served from pre-baked / stock assets; image *generation* (ComfyUI)
    # happens at build time only (see ``scripts/prebake_assets.py``), so
    # the session holds no ComfyUI client.
    visual_manager: VisualManager = field(default_factory=VisualManager)

    # LLM narration enhancer — enabled by default, auto-disables on errors.
    llm_client: LLMClient = field(default_factory=LLMClient)
    use_llm: bool = True

    # Narrative journal (Phase 24A) — temporal continuity: rolling
    # rendered prose + scene/day/week summaries. Distinct from the arc
    # context (``arc_graph`` / ``OutcomeRecord.arc_summary``), which
    # tracks long-running threads. Both feed LLM grounding separately.
    journal: NarrativeJournal = field(default_factory=NarrativeJournal)

    # Background pipeline — wired in by ``new_game`` / ``deserialise``.
    # ``background_generator`` is None when no scene specs are loaded; the
    # session degrades gracefully (events with location cues simply skip
    # the background lookup).
    scene_specs: dict[str, SceneGraphSpec] = field(default_factory=dict)
    background_manifest: BackgroundManifest | None = None
    background_generator: BackgroundGenerator | None = None
    figure_manifest: "FigureManifest | None" = None  # set by ``init_backgrounds``
    grades_root: Path | None = None  # set by ``init_backgrounds``
    overlays_root: Path | None = None  # set by ``init_backgrounds``
    # Prebaked mode (Phase 23): every cue resolves to the canonical
    # per-spec graph (graph_id == spec_id) the pack baked, instead of
    # creating marquee/ad-hoc graphs. Set by ``init_backgrounds``.
    _prebaked: bool = False

    # During match play the status bar swaps from the clock to a label
    # (e.g. "Match vs Northgate"). Set by the match flow (Phase 11.5B);
    # cleared after the match block ends.
    _active_match_label: str | None = None
    _opponent_name: str = "the opposition"

    # Player stance resolved for the current event (Phase 24C). Set by
    # ``resolve_player_stance`` at event start and read by the figure /
    # intro paths + stamped onto the outcome record. Transient — the
    # persistent record lives on ``OutcomeRecord.player_stance``.
    _current_player_stance: PlayerStance | None = None

    # Set by ``enter_slot`` and consumed by the next ``resolve_scene``
    # that resolves a real ``LocationCue``. Implements the auto-teleport
    # rule: arriving at a slot's anchored event is free regardless of
    # where the player was. Transient — not persisted.
    _pending_slot_teleport: bool = False
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
        customisation: PlayerCustomisation | None = None,
        sport: Sport = Sport.SOCCER,
        league_config: LeagueConfig | None = None,
    ) -> "GameSession":
        """Bootstrap a fresh game.

        When ``roster`` is provided the legacy path runs: the caller's
        handcrafted characters are injected directly (useful for tests
        and the old Ren'Py start label). When ``roster`` is ``None`` the
        full 18A/B/C pipeline fires: ``generate_roster`` builds the
        squad, ``generate_secret_web`` weaves a secret network, and the
        player character picks up any overrides from ``customisation``.

        ``customisation`` lets the Ren'Py opening flow pin individual
        axes (name, role, quirks, starting stats) while leaving the rest
        to randomisation. ``player_name`` is always used as the display
        name even when ``customisation.name`` is set.
        """
        from .character_factory import generate_character

        rng = _random.Random(seed)
        np_rng = np.random.default_rng(seed)

        root = content_root or Path(__file__).parent.parent / "content"
        blueprints = load_blueprints_from_path(root / "events")
        templates = load_templates_from_path(root / "templates")
        scene_specs = _load_scene_specs_safe(root / "scenes")
        arc_graph = build_arc_graph(blueprints)

        # --- Build the cast -----------------------------------------------

        if roster is not None:
            # Legacy path: caller provides a handcrafted roster.
            player_role = (
                customisation.role
                if customisation is not None and customisation.role is not None
                else CharacterRole.STRIKER
            )
            player_gp = (
                customisation.gender_presentation.value
                if customisation is not None and customisation.gender_presentation is not None
                else "masculine"
            )
            player = TierACharacter(
                id="player",
                name=player_name,
                role=player_role,
                stats={sn: StatTuple(value=0.5) for sn in StatName},
                gender_presentation=player_gp,
            )
            characters: dict[str, Character] = {"player": player}
            characters.update(roster)
        else:
            # Full pipeline: generate the squad from the master seed.
            from .character_factory import quirks_for_disposition, random_descriptor

            player_role = (
                customisation.role
                if customisation is not None and customisation.role is not None
                else CharacterRole.STRIKER
            )
            player_quirks = (
                customisation.quirks
                if customisation is not None and customisation.quirks is not None
                else None
            )
            # If no explicit quirks but a disposition was chosen, derive
            # thematic quirks from the disposition.
            if (
                player_quirks is None
                and customisation is not None
                and customisation.disposition is not None
            ):
                player_quirks = quirks_for_disposition(
                    customisation.disposition, rng
                )
            player_gender = (
                customisation.gender_presentation
                if customisation is not None and customisation.gender_presentation is not None
                else None
            )
            player_descriptor = random_descriptor(
                rng, gender_presentation=player_gender
            )
            generated_roster = generate_roster(
                rng,
                sport=sport,
                with_player=True,
                player_role=player_role,
                player_name=(player_name.split()[0], player_name.split()[-1])
                if " " in player_name
                else (player_name, ""),
                player_id="player",
                player_descriptor=player_descriptor,
                player_quirks=player_quirks,
            )

            # Apply player customisation overrides.
            player = generated_roster.player
            assert player is not None
            player.name = player_name
            if player_quirks is not None:
                player.quirks = list(player_quirks)
            if (
                customisation is not None
                and customisation.stats is not None
            ):
                for sn, val in customisation.stats.items():
                    if sn in player.stats:
                        player.stats[sn] = StatTuple(value=val)

            characters = {c.id: c for c in generated_roster.all_characters()}

        state = GameState(
            characters=characters,
            week_phase=WeekPhase(season=1, week=1),
        )

        # --- League + season (only on the generated path) -----------------

        if roster is None:
            lc = league_config or LeagueConfig()
            skill_low, skill_high = TIER_SKILL_RANGES[lc.tier]
            opponent_clubs = generate_season_opponents(
                rng,
                count=lc.opponent_count,
                sport=sport,
                skill_range=(skill_low, skill_high),
            )
            season = generate_season(rng, lc, opponent_clubs)
            state.season = season

        # --- Secret web (only on the generated path) ----------------------

        if roster is None:
            character_label = f"{player_name} — {player_role.value}"
            secrets, placeholders = generate_secret_web(
                rng,
                characters=characters,
                character_label=character_label,
            )
            state.secrets = secrets
            state.placeholders = placeholders

        session = cls(
            state=state,
            schedule=None,
            arc_graph=arc_graph,
            blueprints=blueprints,
            templates=templates,
            rng=rng,
            np_rng=np_rng,
            sport=sport,
            scene_specs={s.spec_id: s for s in scene_specs},
        )
        # Wire the stock face pool into the visual manager (pre-baked art).
        stock_root = root.parent / "assets" / "stock_faces"
        session.visual_manager.stock_pool = StockFacePool.load(stock_root)
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
        data["journal"] = self.journal.to_dict()
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
        session.use_llm = bool(data.get("use_llm", True))
        session.journal = NarrativeJournal.from_dict(data.get("journal"))
        # Wire the stock face pool into the visual manager (pre-baked art).
        stock_root = root.parent / "assets" / "stock_faces"
        session.visual_manager.stock_pool = StockFacePool.load(stock_root)
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
        # Advance the season's match-week pointer.
        if self.state.season is not None:
            self.state.season.advance_week()

    # ------------------------------------------------------------------
    # Event selection & resolution
    # ------------------------------------------------------------------

    def blueprints_for_block(self, block_type: BlockType) -> list[EventBlueprint]:
        """Return blueprints whose tags overlap the block's expected set.

        In-match blueprints (``IN_MATCH_TAGS``) are excluded — they
        belong to the match block's phase hooks, not schedule slots.
        """
        allowed = BLOCK_TAGS.get(block_type, set())
        if not allowed:
            return []
        return [
            bp
            for bp in self.blueprints
            if bp.tags & allowed and not bp.tags & IN_MATCH_TAGS
        ]

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
        # Stamp the resolved stance (or the anchor when unresolved) so the
        # next event can bias toward continuity (Phase 24C), then clear the
        # per-event cache so it can't leak into the next event.
        record.player_stance = self._active_player_stance(blueprint).value
        self._current_player_stance = None

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

        Sets the auto-teleport flag so the first ``resolve_scene`` in
        this slot pays no movement cost — the character "shows up" for
        appointments without spending the usual 30-min between-graph
        traversal.

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
        # Mark the slot transition regardless of whether the clock
        # actually advanced — the next event in this slot still gets
        # the free arrival.
        self._pending_slot_teleport = True
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
        prebaked: bool = False,
    ) -> None:
        """Wire the background manifest + generator at game-setup time.

        Ren'Py calls this once during boot with the project's assets dir.
        Tests pass a tmp_path so generated placeholders don't pollute the
        repo. Idempotent — re-running rebuilds against the on-disk
        manifest, useful after a save load.

        ``prebaked`` (Phase 23) is the shipped-build path: load the
        packaged manifest read-only, use a ``PrebakedImageProducer`` (no
        GPU, no network) and a ``NoOpPrefetchScheduler`` (nothing to
        generate), and skip marquee warm-up (assets already on disk).

        Image *generation* (ComfyUI) is a build-time concern only — see
        ``scripts/prebake_assets.py``, which wires a ``ComfyUIImageProducer``
        directly. At runtime an explicit ``producer`` wins; otherwise the
        in-process ``PlaceholderImageProducer`` is used (so dev sessions
        without baked assets still get solid-colour stand-ins).

        ``prefetch_scheduler`` defaults to ``DeferredPrefetchScheduler``
        so prefetch jobs queue up and ``drain_background_prefetch`` runs
        them on idle ticks.

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
            self.overlays_root = None
            return
        assets_root = Path(assets_root)
        manifest = BackgroundManifest.load(assets_root)
        self.background_manifest = manifest

        if prebaked:
            if producer is None:
                producer = PrebakedImageProducer()
            if prefetch_scheduler is None:
                prefetch_scheduler = NoOpPrefetchScheduler()
        if producer is None:
            producer = PlaceholderImageProducer()

        self.background_generator = BackgroundGenerator(
            manifest=manifest,
            specs=self.scene_specs,
            producer=producer,
            prefetch_scheduler=prefetch_scheduler or DeferredPrefetchScheduler(),
        )
        # Render the colour-grade and overlay PNGs alongside the other
        # generated visual assets. Both have version-keyed caches so
        # subsequent boots are effectively free.
        self.grades_root = assets_root.parent / "grades"
        generate_grade_pngs(self.grades_root)
        self.overlays_root = assets_root.parent / "overlays"
        generate_overlay_pngs(self.overlays_root)
        self._prebaked = prebaked
        # Figure assets live alongside backgrounds (game/assets/figures);
        # load the manifest read-only (empty if not baked yet).
        self.figure_manifest = FigureManifest.load(assets_root.parent / "figures")
        # In prebaked mode the pack already holds every marquee asset, so
        # warm-up (which schedules generation) is a no-op.
        if warm_marquees and not prebaked:
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
        fixed `graph_id`; ad-hoc cues create a fresh graph (closed after
        ``release_scene``).

        When the blueprint has no explicit ``location`` but declares
        ``valid_scene_types``, a matching scene spec is selected and an
        ad-hoc ``LocationCue`` is synthesised automatically.

        Side effects:

        - Advances the clock by the movement cost from the player's
          previous location to the cue's resolved location (5 min within
          a graph, 30 min between graphs, 0 for the first scene of a
          slot or the first scene of the game).
        - Updates ``state.current_location`` to the resolved target.
        - Consumes ``_pending_slot_teleport`` so subsequent moves in the
          same slot pay the normal cost.
        """
        cue = blueprint.location
        if cue is None and blueprint.valid_scene_types:
            cue = self._cue_from_scene_types(blueprint.valid_scene_types)
        if cue is None or self.background_manifest is None:
            return None
        if cue.spec_id not in self.scene_specs:
            return None

        if self._prebaked:
            # Every cue for a spec resolves to the canonical pre-baked
            # graph (graph_id == spec_id) the pack holds with alternates.
            # Marquee vs ad-hoc collapses — all suburban houses share the
            # baked suburban_house set (accepted full-pre-bake tradeoff).
            graph_id = cue.spec_id
            if self.background_manifest.get_graph(graph_id) is None:
                # Spec wasn't baked — create empty so the read-only
                # producer placeholders gracefully instead of failing.
                self.background_manifest.create_graph(
                    cue.spec_id, self._descriptor_for(cue), graph_id=graph_id
                )
            target = (graph_id, cue.node_name)
        elif cue.graph_id is not None:
            # Marquee — create the graph on first use.
            if self.background_manifest.get_graph(cue.graph_id) is None:
                descriptor = self._descriptor_for(cue)
                self.background_manifest.create_graph(
                    cue.spec_id, descriptor, graph_id=cue.graph_id
                )
            target = (cue.graph_id, cue.node_name)
        else:
            # Ad-hoc — fresh graph each call.
            descriptor = self._descriptor_for(cue)
            graph = self.background_manifest.create_graph(cue.spec_id, descriptor)
            target = (graph.graph_id, cue.node_name)

        cost = self._movement_cost(target)
        if cost > 0:
            self.state.clock.advance(cost)
        self.state.current_location = target
        self._pending_slot_teleport = False
        return target

    def _movement_cost(self, target: tuple[str, str]) -> int:
        """Compute the movement cost in minutes from current_location to
        ``target``. Used by ``resolve_scene``.

        Cost matrix:
          - first scene ever (current_location is None): 0
          - same graph + same node (revisit): 0
          - same graph, different node: 5 min
          - different graph: 30 min
          - any case while ``_pending_slot_teleport`` is set: 0
        """
        if self._pending_slot_teleport:
            return 0
        src = self.state.current_location
        if src is None:
            return 0
        if src == target:
            return 0
        if src[0] == target[0]:
            return 5
        return 30

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
        `close=True` (use this for ad-hoc graphs after their event ends).

        No-op in prebaked mode: the canonical per-spec graphs are shared
        across every event and must never be reaped or closed, and the
        read-only pack is never rewritten.
        """
        if self.background_manifest is None or self._prebaked:
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

    def overlays_for_scene(
        self, graph_id: str, node_name: str
    ) -> list[tuple[OverlaySpec, Path]]:
        """Return the overlay stack for a given scene as ``(spec, path)``
        pairs, in bottom-to-top compositing order.

        Looks up the graph's ``LocationDescriptor.kind`` for the base
        stack, then merges weather-conditional additions (rain streak
        when raining, heat shimmer in clear midday outdoor scenes).
        Returns an empty list when the pipeline isn't initialised or
        the graph is unknown.
        """
        if (
            self.background_manifest is None
            or self.overlays_root is None
        ):
            return []
        graph = self.background_manifest.get_graph(graph_id)
        if graph is None:
            return []
        kind = graph.descriptor.kind
        atm = self.atmosphere()
        specs = overlays_for(kind, atm)
        return [
            (spec, overlay_path(self.overlays_root, spec.overlay))
            for spec in specs
        ]

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

    def _cue_from_scene_types(self, scene_types: list) -> LocationCue | None:
        """Synthesise an ad-hoc ``LocationCue`` from ``valid_scene_types``.

        Tries each scene type in order, mapping via
        ``location_kind_for_scene_type`` and then checking whether a
        matching ``SceneGraphSpec`` is loaded. Returns the first match
        or ``None`` if no spec is available.
        """
        for st in scene_types:
            kind = location_kind_for_scene_type(st)
            if kind is None:
                continue
            for spec in self.scene_specs.values():
                if spec.kind == kind:
                    node = spec.entry_nodes[0] if spec.entry_nodes else spec.nodes[0]
                    return LocationCue(spec_id=spec.spec_id, node_name=node)
        return None

    def _descriptor_for(self, cue: LocationCue) -> LocationDescriptor:
        base = self.default_location_descriptors.get(cue.spec_id)
        if base is None:
            spec = self.scene_specs[cue.spec_id]
            base = LocationDescriptor(kind=spec.kind)
        merged = base.to_dict()
        # Apply instance-level style overrides (socioeconomic, mood, palette)
        if cue.scene_instance is not None:
            from .scene_taxonomy import SceneInstance, descriptor_overrides_for_instance
            try:
                instance = SceneInstance(cue.scene_instance)
                instance_overrides = descriptor_overrides_for_instance(instance)
                merged.update(instance_overrides)
            except ValueError:
                pass  # unknown instance value — ignore
        # Explicit per-event overrides take priority
        if cue.descriptor_overrides:
            merged.update(cue.descriptor_overrides)
        return LocationDescriptor.from_dict(merged)

    def _narrate_text_beat(
        self,
        text: str,
        blueprint: EventBlueprint,
        cast: Mapping[str, Character],
        *,
        templates: "Sequence[NarrativeTemplate] | None" = None,
        trigger_outcome: OutcomeRecord | None = None,
    ) -> list[str]:
        """Narrate one beat of authored text and fold it into the journal.

        Shared by the setup / action / reaction / result beats (Phase
        24B). ``text`` becomes the ``{summary}`` source (so role-scoped
        pronoun slots resolve); ``templates`` lets the result beat run
        through the event's template pool, while the action/reaction/setup
        beats pass ``None`` (the authored text is itself the prose and is
        only LLM-polished). Recent journal context grounds every beat so
        each flows from the last; the rendered pages are then recorded so
        the *next* beat continues from them.
        """
        player = cast.get("player")
        ctx = build_narration_context(
            target=player,
            cast=cast,
            outcome_log=self.state.outcome_log,
            trigger_outcome=trigger_outcome,
            team_morale=self.team_morale,
            branch_summary=text,
            location=(
                blueprint.location.node_name
                if blueprint.location is not None
                else None
            ),
        )
        pages = narrate(
            templates if templates is not None else [],
            ctx,
            self.rng,
            use_llm=self.use_llm,
            llm_client=self.llm_client,
            event_tags=blueprint.tags,
            recent_narration=self.journal.recent_context(),
        )
        for page in pages:
            self.journal.record_beat(page)
        return pages

    def narrate_outcome(
        self,
        blueprint: EventBlueprint,
        cast: dict[str, Character],
        record: OutcomeRecord,
    ) -> list[str]:
        """Produce paginated narration for a resolved event's result beat.

        Returns a list of screen-sized pages. Short narration yields a
        single-page list; long template fills or LLM rephrasings split
        on sentence boundaries. Callers iterate the list to display each
        page in turn. This is the result beat of :meth:`narrate_event`,
        and the single-beat fallback when a branch authors no extra beats.
        """
        event_templates = templates_for_event(
            self.templates, blueprint.id, blueprint.tags
        )
        return self._narrate_text_beat(
            record.summary,
            blueprint,
            cast,
            templates=event_templates,
            trigger_outcome=record,
        )

    def narrate_setup(
        self,
        blueprint: EventBlueprint,
        cast: Mapping[str, Character],
    ) -> list[str]:
        """Pre-choice premise beat (Phase 24B).

        Narrated after the atmospheric scene intro and before the choice
        menu. Returns ``[]`` when the blueprint authors no ``setup`` — the
        scene intro line then stands as the only pre-choice framing.
        """
        if not blueprint.setup:
            return []
        return self._narrate_text_beat(blueprint.setup, blueprint, cast)

    def narrate_arc_recap(
        self,
        blueprint: EventBlueprint,
        cast: Mapping[str, Character],
    ) -> list[str]:
        """Arc callback beat (Phase 24C) — the thread track made visible.

        When this event resumes an arc thread whose previous beat resolved
        on an *earlier day*, recap that beat so the current scene is read
        in light of what came before. Placed after the scene setup and
        before the choice. Returns ``[]`` when there is no prior arc beat,
        when the prior beat was the same day (no gap to bridge), or when
        no day was recorded (legacy outcomes).

        This is distinct from the journal (immediate continuity): it
        surfaces the arc digest (``OutcomeRecord.arc_summary``), resolved
        against the cast that was present then, framed by how long the
        thread has lapsed.
        """
        prior = find_prior_arc_outcome(
            blueprint.id, self.arc_graph, self.state.outcome_log
        )
        if prior is None or prior.day_ordinal is None:
            return []
        today = (
            self.state.clock.day_ordinal() if self.state.clock is not None else None
        )
        if today is None or prior.day_ordinal >= today:
            return []

        thread = (prior.arc_summary or prior.summary or "").strip()
        if not thread:
            return []
        thread = compress_arc_summary(thread)

        # Resolve the prior thread's pronoun slots against the cast that
        # was present when it happened (current cast fills shared roles).
        recap_cast: dict[str, Character] = dict(cast)
        for role, cid in prior.participants.items():
            ch = self.state.characters.get(cid)
            if ch is not None:
                recap_cast[role] = ch
        ctx = NarrationContext(
            target=recap_cast.get("player"),
            cast=recap_cast,
            branch_summary=thread,
        )
        resolved = _substitute(thread, ctx)

        gap = today - prior.day_ordinal
        recap = f"{_recap_distance_phrase(gap)}: {resolved}"

        if self.use_llm and self.llm_client is not None:
            names = [
                c.nickname or c.name
                for c in recap_cast.values()
                if getattr(c, "name", None)
            ]
            recap = recap_arc(
                self.llm_client,
                recap,
                cast_names=names,
                cast_pronouns=self._cast_pronouns(recap_cast),
            )

        pages = paginate(recap)
        for page in pages:
            self.journal.record_beat(page)
        return pages

    def narrate_event(
        self,
        blueprint: EventBlueprint,
        cast: dict[str, Character],
        record: OutcomeRecord,
    ) -> list["NarratedBeat"]:
        """Ordered post-choice beats: action → reaction → result (24B).

        The optional action/reaction beats play only when the resolved
        branch authors them; the result beat (branch summary, run through
        the template pool) always plays and is the single-beat fallback.
        Each beat is recorded into the journal before the next is
        narrated, so reaction flows from action and result from both.
        Ren'Py iterates the beats and, within each, the pages.
        """
        beats: list[NarratedBeat] = []
        outcome = blueprint.outcomes.get(record.branch_taken)
        if outcome is not None and outcome.action_summary:
            beats.append(NarratedBeat("action", self._narrate_text_beat(
                outcome.action_summary, blueprint, cast, trigger_outcome=record,
            )))
        if outcome is not None and outcome.reaction_summary:
            beats.append(NarratedBeat("reaction", self._narrate_text_beat(
                outcome.reaction_summary, blueprint, cast, trigger_outcome=record,
            )))
        beats.append(
            NarratedBeat("result", self.narrate_outcome(blueprint, cast, record))
        )
        return beats

    def scene_intro(
        self,
        blueprint: EventBlueprint,
        cast: Mapping[str, Character],
    ) -> str:
        """Pre-choice scene setting: place, company, atmosphere.

        Built from data the blueprint already carries (location cue,
        cast, event tone) so no per-blueprint authoring is needed. With
        the LLM enabled, the assembled line is rephrased (grounded with
        location + cast pronouns) so repeated tones still read fresh;
        the assembled line is always the fallback. Returns ``""`` when
        there is nothing worth saying — callers skip the line.
        """
        intro, others = self._assemble_scene_intro(blueprint, cast)

        if intro and self.use_llm and self.llm_client is not None:
            from .llm import enhance_scene_intro

            cue = blueprint.location
            intro = enhance_scene_intro(
                self.llm_client,
                intro,
                cast_names=others,
                location=cue.node_name if cue is not None else None,
                cast_pronouns=self._cast_pronouns(cast),
                arc_summary=self._latest_arc_summary(),
                recent_narration=self.journal.recent_context(),
                perspective_note=_STANCE_PERSPECTIVE.get(
                    self._active_player_stance(blueprint)
                ),
            )
        # The intro opens the scene — record it as the first beat so the
        # outcome narration continues from it (temporal track).
        self.journal.record_beat(intro)
        return intro

    def _latest_arc_summary(self) -> str | None:
        """Most recent arc digest from the outcome log, for grounding the
        thread track (distinct from the journal's temporal track)."""
        for o in reversed(self.state.outcome_log):
            if o.arc_summary:
                return o.arc_summary
        return None

    def close_scene(self, cast: Mapping[str, Character] | None = None) -> str:
        """Scene boundary: compress the open journal beats into a single
        paragraph and reset the verbatim window (Phase 24A).

        Ren'Py calls this at the end of an event (one event == one scene
        for now). The summary is what later scenes ground on once the
        verbatim beats roll off, so the journal stays bounded while still
        carrying continuity. Returns the summary, or ``""`` when there is
        nothing open. Never blocks — deterministic compression is the
        fallback when the LLM is off.
        """
        if not self.journal.has_open_scene():
            return ""
        cast_pronouns: dict[str, str] = {}
        cast_names: list[str] = []
        if cast:
            cast_pronouns = self._cast_pronouns(cast)
            cast_names = list(cast_pronouns)
        client = self.llm_client if (self.use_llm and self.llm_client) else None
        summary = summarise_narration(
            client or LLMClient(enabled=False),
            list(self.journal.recent_beats),
            cast_names=cast_names,
            cast_pronouns=cast_pronouns,
            kind="scene",
        )
        self.journal.record_scene_summary(summary)
        return summary

    def _assemble_scene_intro(
        self,
        blueprint: EventBlueprint,
        cast: Mapping[str, Character],
    ) -> tuple[str, list[str]]:
        """Deterministic intro assembly (no LLM). Returns the intro string
        and the non-player cast display names (for LLM grounding)."""
        parts: list[str] = []
        cue = blueprint.location
        if cue is not None:
            parts.append(cue.node_name.replace("_", " ").capitalize() + ".")
        others = [
            (c.nickname or c.name)
            for role, c in sorted(cast.items())
            if role != "player"
        ]
        if len(others) == 1:
            parts.append(f"With {others[0]}.")
        elif others:
            parts.append("With " + ", ".join(others[:-1]) + f" and {others[-1]}.")
        if blueprint.event_id is not None:
            lines = _TONE_INTRO_LINES.get(blueprint.event_id.tone, ())
            if lines:
                parts.append(self.rng.choice(lines))
        return " ".join(parts), others

    def resolve_player_stance(
        self,
        blueprint: EventBlueprint,
        cast: Mapping[str, Character],
    ) -> PlayerStance:
        """Resolve and cache the player's stance for this event (24C).

        Sampled (RNG-injected) from the blueprint's anchor stance, the
        player's traits, and the prior event's stance (continuity). Called
        once at event start; the figure framing, scene-intro perspective,
        and the stamped outcome record all read the cached result, so they
        agree within an event. Returns the resolved stance.
        """
        player = cast.get("player")
        has_others = any(role != "player" for role in cast)
        stance = weighted_player_stance(
            blueprint,
            player,
            rng=self.rng,
            prior_stance=self._last_player_stance(),
            has_others=has_others,
        )
        self._current_player_stance = stance
        return stance

    def _last_player_stance(self) -> PlayerStance | None:
        """The player's stance in the most recent event that recorded one
        — the continuity anchor for ``resolve_player_stance``."""
        for record in reversed(self.state.outcome_log):
            if record.player_stance:
                try:
                    return PlayerStance(record.player_stance)
                except ValueError:
                    return None
        return None

    def _active_player_stance(self, blueprint: EventBlueprint) -> PlayerStance:
        """The resolved stance for the current event, or the blueprint
        anchor when none was resolved (tests / non-stance flows)."""
        return self._current_player_stance or blueprint.player_stance

    _DEFAULT_DESCRIPTOR = CharacterDescriptor()

    def figure_layout_for(
        self,
        blueprint: EventBlueprint,
        cast: Mapping[str, Character],
        canvas_w: int,
        canvas_h: int,
        *,
        distance: FigureDistance = FigureDistance.NORMAL,
        max_npcs: int = 2,
    ) -> list[tuple[str, "FigureBox", str]]:
        """Resolve the figures to composite for an event.

        Returns ``(image_path, box, role)`` per figure, ordered NPCs-first
        then the player anchor, so Ren'Py can draw the player on top.
        Selection maps each cast member's persisted descriptor + the
        event tone to a baked figure; figures with no available asset are
        skipped. Returns ``[]`` if the figure pack isn't loaded.
        """
        if self.figure_manifest is None or not self.figure_manifest.assets:
            return []
        tone = (
            blueprint.event_id.tone
            if blueprint.event_id is not None
            else EventTone.NEUTRAL
        )
        # Scene dress context (locker/shower → context-appropriate figures).
        context = context_for_node(
            blueprint.location.node_name if blueprint.location is not None else None
        )

        def desc_of(c: Character) -> CharacterDescriptor:
            return getattr(c, "descriptor", None) or self._DEFAULT_DESCRIPTOR

        # NPCs first (focal roles preferred), then the player anchor last.
        resolved: list[tuple[FigureSlot, str, str]] = []
        others = [
            (role, c) for role, c in cast.items() if role != "player"
        ]
        others.sort(key=lambda rc: (rc[0] not in _FOCAL_ROLE_PRIORITY, rc[0]))
        for role, c in others[:max_npcs]:
            asset = select_for_character(
                self.figure_manifest, desc_of(c), c.role, tone, context=context,
            )
            if asset is not None:
                resolved.append((FigureSlot(role="npc"), asset.path, "npc"))

        player = cast.get("player")
        if player is not None:
            asset = select_figure(
                self.figure_manifest,
                FigureCategory.PLAYER,
                appearance_from_descriptor(desc_of(player)),
                FigurePosture.NEUTRAL,
                context,
            )
            if asset is not None:
                resolved.append(
                    (FigureSlot(role="player"), asset.path, "player")
                )

        if not resolved:
            return []
        framing = _STANCE_TO_FRAMING.get(
            self._active_player_stance(blueprint), PlayerFraming.FOREGROUND
        )
        boxes = compute_layout(
            canvas_w, canvas_h, [s for s, _, _ in resolved],
            distance=distance,
            player_framing=framing,
        )
        return [
            (str(self.figure_manifest.resolve(path)), box, role)
            for (_, path, role), box in zip(resolved, boxes)
        ]

    @staticmethod
    def _cast_pronouns(cast: Mapping[str, Character]) -> dict[str, str]:
        """Map each cast member's display name to its pronoun set, for
        grounding the LLM so it doesn't infer gender from names."""
        sets = {
            "masculine": "he/him",
            "feminine": "she/her",
            "androgynous": "they/them",
        }
        out: dict[str, str] = {}
        for c in cast.values():
            name = getattr(c, "nickname", None) or getattr(c, "name", None)
            if not name:
                continue
            gp = str(getattr(c, "gender_presentation", "") or "masculine")
            out[name] = sets.get(gp, "they/them")
        return out

    def focal_character(
        self, cast: Mapping[str, Character]
    ) -> Character | None:
        """The non-player cast member a scene should put on screen.

        Prefers the conventional counterpart roles; falls back to the
        first non-player role alphabetically; ``None`` for solo scenes.
        """
        for role in _FOCAL_ROLE_PRIORITY:
            if role in cast:
                return cast[role]
        for role in sorted(cast):
            if role != "player":
                return cast[role]
        return None

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
        self._opponent_name = opponent_name

    def setup_match_from_season(self) -> str | None:
        """Set up this week's match from the season fixture list.

        Returns the opponent's club name, or ``None`` if no fixture
        exists for the current season week (e.g. bye week or season
        complete). Falls back to generic opponent if no season is
        loaded.
        """
        season = self.state.season
        if season is None:
            self.setup_match()
            return None
        fixture = season.current_fixture()
        if fixture is None:
            self.setup_match()
            return None
        opp_name = fixture.opponent_of(season.config.club_name)
        if opp_name is None:
            self.setup_match()
            return None
        opp_club = season.opponent_club_by_name(opp_name)
        if opp_club is not None:
            self.setup_match(
                opponent=opp_club.seeds, opponent_name=opp_name,
            )
        else:
            self.setup_match(opponent_name=opp_name)
        return opp_name

    def roster_players(self) -> list[Character]:
        """Return every character in state (players + staff + drama NPCs)."""
        return list(self.state.characters.values())

    def playing_squad(self) -> list[Character]:
        """Characters eligible to take the field, in stable roster order.

        Filters :meth:`roster_players` down to actual playing roles by
        dropping :data:`NON_PLAYING_ROLES` (manager, physio, assistant
        coach, media, family, other). This is the *single source of
        truth* for the match: ``simulate_phase`` is fed this list, so
        ``PhaseResult.goal_scorer_index`` indexes into it — every
        consumer of that index (``narrate_match_phase``,
        ``_scorer_character``, ``evaluate_match``) must filter through
        the same method or the rows won't line up.

        Roster membership doesn't change mid-match, so dict insertion
        order makes this deterministic across calls within a match.
        """
        return [c for c in self.roster_players() if c.role not in NON_PLAYING_ROLES]

    def simulate_game_phase(self, phase_index: int, total_phases: int = 8) -> PhaseResult:
        """Run one phase of the match simulation.

        Returns a ``PhaseResult`` for Ren'Py to display.
        """
        players = self.playing_squad()
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

    def narrate_match_phase(
        self, result: PhaseResult, phase_index: int, total_phases: int = 8
    ) -> str:
        """Narrated line for a simulated phase (Phase 22F).

        Resolves the scorer's display name and the opponent label, then
        delegates to :func:`engine.narrative.narrate_match_phase`.
        """
        scorer_name: str | None = None
        if result.goal_scored and result.goal_scorer_index is not None:
            players = self.playing_squad()
            if result.goal_scorer_index < len(players):
                scorer = players[result.goal_scorer_index]
                scorer_name = scorer.nickname or scorer.name
        return narrate_match_phase(
            result,
            self.rng,
            scorer_name=scorer_name,
            opponent_name=self._opponent_name,
            phase_index=phase_index,
            total_phases=total_phases,
        )

    def narrate_self_evaluation(self, perceived: float) -> str:
        """Narrated post-match self-evaluation line (Phase 22F)."""
        return self_evaluation_line(perceived, self.rng)

    # ------------------------------------------------------------------
    # In-phase match events (Phase 22F)
    # ------------------------------------------------------------------

    def _ingame_blueprints(self) -> list[EventBlueprint]:
        """Blueprints that resolve inside the match block (``ingame`` tag)."""
        return [bp for bp in self.blueprints if bp.tags & IN_MATCH_TAGS]

    def select_match_event(
        self, result: PhaseResult, phase_index: int, total_phases: int = 8
    ) -> EventBlueprint | None:
        """Pick a playable in-phase event for a just-simulated phase, or None.

        Currently triggers on a teammate goal (the player being mobbed is
        a different beat, deferred). Gated by ``MATCH_EVENT_GOAL_CHANCE``
        so not every goal interrupts play; weight-sampled from the
        ``ingame`` pool through the normal prereq/recency machinery so
        repeats are naturally dampened.
        """
        if not result.goal_scored:
            return None
        scorer = self._scorer_character(result)
        # Only trigger when a *teammate* scored — the player being the
        # scorer is a separate beat we don't author yet.
        if scorer is None or scorer.id == "player":
            return None
        if self.rng.random() > MATCH_EVENT_GOAL_CHANCE:
            return None
        candidates = self._ingame_blueprints()
        if not candidates:
            return None
        return select_event(candidates, self._game_context(), self.state, self.rng)

    def cast_match_event(
        self, blueprint: EventBlueprint, result: PhaseResult
    ) -> dict[str, Character] | None:
        """Cast an in-match event, pinning the real scorer to ``scorer``."""
        pinned: dict[str, Character] = {}
        scorer = self._scorer_character(result)
        if scorer is not None and any(
            s.role == "scorer" for s in blueprint.participants
        ):
            pinned["scorer"] = scorer
        return cast_event(blueprint, self.state, self.rng, pinned=pinned)

    def resolve_match_event(
        self,
        blueprint: EventBlueprint,
        branch: str,
        cast: dict[str, Character],
    ) -> OutcomeRecord:
        """Resolve an in-match event: apply effects, log the record.

        Unlike :meth:`resolve_event` there is no schedule slot to mark and
        no clock advance — the match block consumes its whole afternoon as
        a single unit, so in-phase beats happen "for free" within it.
        """
        prior = find_prior_arc_outcome(
            blueprint.id, self.arc_graph, self.state.outcome_log
        )
        return resolve_outcome(blueprint, branch, cast, self.state, prior)

    def _scorer_character(self, result: PhaseResult) -> Character | None:
        if not result.goal_scored or result.goal_scorer_index is None:
            return None
        # ``goal_scorer_index`` indexes the playing squad fed to
        # ``simulate_phase`` — never the full roster — so staff can't be
        # resolved as a scorer (and the pinned ``scorer`` always satisfies
        # the ``teammate()`` cast filter for in-match beats).
        players = self.playing_squad()
        if 0 <= result.goal_scorer_index < len(players):
            return players[result.goal_scorer_index]
        return None

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

        # Average performance across phases for each player. Must use the
        # same squad the phases were simulated with so the performance
        # rows line up with the character list.
        players = self.playing_squad()
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

        # Record result in the season table + simulate other league
        # fixtures for this week.
        self._record_match_in_season()

        return {
            "perceived": perceived,
            "mood_delta": mood_delta,
            "morale_delta": morale_delta,
            "team_goals": self.team_goals,
            "opp_goals": self.opp_goals,
            "team_morale": self.team_morale,
        }

    def _record_match_in_season(self) -> None:
        """Record the player's match result + simulate other fixtures."""
        season = self.state.season
        if season is None:
            return
        season.record_result(
            season.current_week, self.team_goals, self.opp_goals,
        )
        season.simulate_other_results(season.current_week, self.rng)

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
