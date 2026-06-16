# Game block — match simulation across all phases.
#
# Called once per match. Runs 8 (default) phases of simulation and
# shows a summary per phase. No simulation math here — the engine
# does everything via fh.session.simulate_game_phase().

label game_block:
    # Set up opponents from the season fixture list. Falls back to a
    # generic opponent if no season is loaded (legacy/test path).
    $ opp_name = fh.session.setup_match_from_season()
    if opp_name is None:
        $ opp_name = "Opponent"

    e "The match is about to begin."

    $ total_phases = 8
    $ phase_idx = 0

    label .phase_loop:
        if phase_idx >= total_phases:
            jump .match_summary

        $ result = fh.session.simulate_game_phase(phase_idx, total_phases)

        # Narrated phase line (Phase 22F) — the engine reads the balance
        # of play, momentum, and any goal; no stat readouts here.
        $ phase_line = fh.session.narrate_match_phase(result, phase_idx, total_phases)
        e "[phase_line]"

        # In-phase playable beat (Phase 22F) — a teammate goal may open a
        # quick choice (e.g. join the huddle). Engine decides whether one
        # fires; this only displays it.
        $ fh.bp = fh.session.select_match_event(result, phase_idx, total_phases)
        if fh.bp is not None:
            call match_event(result) from _call_match_event

        $ phase_idx += 1
        jump .phase_loop

    label .match_summary:
        $ eval_result = fh.session.evaluate_match()
        $ fh_checkpoint()
        $ tg = fh.session.team_goals
        $ og = fh.session.opp_goals

        if tg > og:
            e "Full time: Victory! [tg]–[og]."
        elif tg < og:
            e "Full time: Defeat. [tg]–[og]."
        else:
            e "Full time: Draw. [tg]–[og]."

        $ self_eval_line = fh.session.narrate_self_evaluation(eval_result["perceived"])
        e "[self_eval_line]"

        return


# In-phase match beat (Phase 22F). fh.bp holds the selected ingame
# blueprint; result is the phase that triggered it (carries the scorer).
label match_event(result):
    $ cast = fh.session.cast_match_event(fh.bp, result)
    if cast is None:
        $ fh.bp = None
        return

    # Put the scorer on screen for the moment.
    $ focal = fh.session.focal_character(cast)
    if focal is not None:
        call show_character(focal, mood=fh.session.team_morale) from _call_show_focal_match

    $ branch = fh_choose_branch(fh.session.get_choices(fh.bp))
    $ record = fh.session.resolve_match_event(fh.bp, branch, cast)

    $ pages = fh.session.narrate_outcome(fh.bp, cast, record)
    python:
        for page in pages:
            renpy.say(e, page)

    if focal is not None:
        hide character_sprite
    $ fh.bp = None
    return
