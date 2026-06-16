# Field & Heart — main game loop (technical §7.2)
#
# This is the top-level Ren'Py entry point. It instantiates the engine
# once and delegates ALL logic to it. No stat math, event selection, or
# narration assembly happens in .rpy files.

init python:
    import sys, os

    # Make the engine importable from the game directory.
    game_dir = os.path.join(config.gamedir)
    if game_dir not in sys.path:
        sys.path.insert(0, game_dir)

    from engine.session import GameSession, PlayerCustomisation
    from engine.schedule import BlockType
    from engine.characters import CharacterRole, Disposition
    from engine.simulation import Sport
    from engine.league import LeagueConfig, LeagueFormat, LeagueTier
    from engine.sprite_pool import GenderPresentation

define e = Character("Narrator", color="#c8ffc8")


# --- New game ---------------------------------------------------------------

label start:
    # --- Player setup ---
    $ player_name = ""
    $ player_role = CharacterRole.STRIKER
    $ player_gender = GenderPresentation.MASCULINE
    $ player_disposition = Disposition.COMPETITIVE
    $ chosen_sport = Sport.SOCCER
    $ chosen_tier = LeagueTier.SEMI_PRO
    $ chosen_format = LeagueFormat.OPEN
    $ club_name = "Ashworth Town"

    menu:
        "How do you present yourself?"

        "Masculine":
            $ player_gender = GenderPresentation.MASCULINE
        "Feminine":
            $ player_gender = GenderPresentation.FEMININE
        "Androgynous":
            $ player_gender = GenderPresentation.ANDROGYNOUS

    python:
        player_name = renpy.input("What is your name?", default="Alex Morgan", length=40)
        player_name = player_name.strip() or "Alex Morgan"

    menu:
        "What kind of personality do you have?"

        "Competitive — driven to win, pushes hard":
            $ player_disposition = Disposition.COMPETITIVE
        "Fiery — passionate, intense, quick to react":
            $ player_disposition = Disposition.FIERY
        "Calm — composed under pressure, steady":
            $ player_disposition = Disposition.CALM
        "Warm — team player, builds bonds easily":
            $ player_disposition = Disposition.WARM
        "Guarded — careful, keeps people at arm's length":
            $ player_disposition = Disposition.GUARDED
        "Withdrawn — quiet, introspective, hard to read":
            $ player_disposition = Disposition.WITHDRAWN

    menu:
        "Choose your sport:"

        "Soccer":
            $ chosen_sport = Sport.SOCCER
        "Rugby":
            $ chosen_sport = Sport.RUGBY
        "Basketball":
            $ chosen_sport = Sport.BASKETBALL

    menu:
        "Choose your position:"

        "Striker":
            $ player_role = CharacterRole.STRIKER
        "Midfielder":
            $ player_role = CharacterRole.MIDFIELDER
        "Defender":
            $ player_role = CharacterRole.DEFENDER
        "Goalkeeper":
            $ player_role = CharacterRole.GOALKEEPER

    menu:
        "Choose your league level:"

        "Professional — elite competition, high pressure":
            $ chosen_tier = LeagueTier.PROFESSIONAL
        "Semi-Professional — competitive, balanced":
            $ chosen_tier = LeagueTier.SEMI_PRO
        "Amateur — grassroots, community feel":
            $ chosen_tier = LeagueTier.AMATEUR

    menu:
        "League format:"

        "Open — promotion and relegation":
            $ chosen_format = LeagueFormat.OPEN
        "Closed — fixed membership":
            $ chosen_format = LeagueFormat.CLOSED

    python:
        club_name = renpy.input("Your club's name?", default="Ashworth Town", length=40)
        club_name = club_name.strip() or "Ashworth Town"

    # Generate the world from a master seed. The full roster, coaching
    # staff, secret web, and league season are produced deterministically.
    # The session lives on `fh` (runtime.rpy) — never in the store, which
    # Ren'Py pickles on save.
    python:
        renpy.not_infinite_loop(600)
        master_seed = int(time.time()) & 0xFFFFFFFF

        fh.session = GameSession.new_game(
            player_name,
            seed=master_seed,
            customisation=PlayerCustomisation(
                name=player_name,
                role=player_role,
                gender_presentation=player_gender,
                disposition=player_disposition,
            ),
            sport=chosen_sport,
            league_config=LeagueConfig(
                club_name=club_name,
                league_format=chosen_format,
                tier=chosen_tier,
            ),
        )

    # Wire the background pipeline (uses ComfyUI when available).
    python:
        renpy.not_infinite_loop(600)
        fh_init_backgrounds()

    # Show the persistent status bar overlay.
    show screen status_bar

    e "Welcome to Field & Heart."
    e "Season [fh.session.state.week_phase.season], Week [fh.session.state.week_phase.week]."

    jump week_loop


# --- Week loop ---------------------------------------------------------------

default slot_idx = 0

label week_loop:
    $ schedule = fh.session.start_week()
    $ fh_checkpoint()
    e "A new week begins."

    # Show the upcoming fixture if a season is loaded.
    if fh.session.state.season is not None:
        $ season = fh.session.state.season
        $ fixture = season.current_fixture()
        if fixture is not None:
            $ opp = fixture.opponent_of(season.config.club_name)
            if fixture.home == season.config.club_name:
                e "This week: [season.config.club_name] vs [opp] (Home)"
            else:
                e "This week: [opp] vs [season.config.club_name] (Away)"
        $ pos = season.player_position()
        $ total = season.config.total_clubs
        $ season = None
        e "League position: [pos] of [total]"

    # Process each slot in order.
    $ slot_idx = 0

    label .next_slot:
        if slot_idx >= len(schedule.slots):
            jump week_end

        $ slot = schedule.slots[slot_idx]

        # Fast-forward the world clock to this slot's anchor (no-op if
        # we're already at or past the anchor on the right weekday).
        # Match phases share Sat afternoon — only the first one needs
        # to advance; the rest are inside the same block.
        if slot.block_type != BlockType.GAME_PHASE or slot.phase_index == 0:
            $ fh.session.enter_slot(slot_idx)

        # Route by block type.
        if slot.block_type == BlockType.DRAMA:
            call drama_block(slot_idx) from _call_drama
        elif slot.block_type == BlockType.TRAINING:
            call drama_block(slot_idx) from _call_training
        elif slot.block_type == BlockType.PREGAME:
            call drama_block(slot_idx) from _call_pregame
        elif slot.block_type == BlockType.GAME_PHASE:
            # Game phases are batched — jump to game_block which
            # processes all 8 phases, then skip past them.
            if slot.phase_index == 0:
                call game_block from _call_game
                # Skip remaining game-phase slots.
                python:
                    while slot_idx < len(schedule.slots) and schedule.slots[slot_idx].block_type == BlockType.GAME_PHASE:
                        slot_idx += 1
                jump .next_slot
        elif slot.block_type == BlockType.POSTGAME:
            call postgame_block(slot_idx) from _call_postgame
        elif slot.block_type == BlockType.DOWNTIME:
            call drama_block(slot_idx) from _call_downtime

        $ slot_idx += 1
        jump .next_slot


# --- Resume after a native load ----------------------------------------------
#
# after_load (runtime.rpy) rebuilds fh.session from the save blob and
# jumps here. Re-point the store's schedule reference at the rebuilt
# session and re-enter the slot loop at the restored slot_idx.

label week_resume:
    $ schedule = fh.session.schedule
    if schedule is None:
        jump week_loop
    jump week_loop.next_slot


# --- End of week -------------------------------------------------------------

label week_end:
    e "End of week [fh.session.state.week_phase.week]."

    menu:
        "Continue to next week":
            $ fh.session.advance_week()
            jump week_loop

        "Save and quit":
            call save_game from _call_save
            return
