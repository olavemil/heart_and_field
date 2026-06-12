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
