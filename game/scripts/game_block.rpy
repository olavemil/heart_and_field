# Game block — match simulation across all phases.
#
# Called once per match. Runs 8 (default) phases of simulation and
# shows a summary per phase. No simulation math here — the engine
# does everything via session.simulate_game_phase().

label game_block:
    # Set up opponents.
    $ session.setup_match(opponent_rating=0.5)

    e "The match is about to begin."

    $ total_phases = 8
    $ phase_idx = 0

    label .phase_loop:
        if phase_idx >= total_phases:
            jump .match_summary

        $ result = session.simulate_game_phase(phase_idx, total_phases)

        # Build a phase report string.
        $ phase_num = phase_idx + 1
        $ team_perf = "{:.0f}".format(result.team_perf * 100)
        $ opp_perf = "{:.0f}".format(result.opp_perf * 100)
        $ mom = "{:+.0f}".format(result.momentum * 100)

        if result.goal_scored:
            $ scorer_idx = result.goal_scorer_index
            $ players = session.roster_players()
            if scorer_idx is not None and scorer_idx < len(players):
                $ scorer_name = players[scorer_idx].name
            else:
                $ scorer_name = "Someone"
            e "Phase [phase_num]: GOAL! [scorer_name] scores! (Team [team_perf]%% — Opp [opp_perf]%% | Momentum [mom]%%)"
        else:
            e "Phase [phase_num]: Team [team_perf]%% — Opp [opp_perf]%% | Momentum [mom]%%"

        $ phase_idx += 1
        jump .phase_loop

    label .match_summary:
        $ eval_result = session.evaluate_match()
        $ tg = session.team_goals
        $ og = session.opp_goals

        if tg > og:
            e "Full time: Victory! [tg]–[og]."
        elif tg < og:
            e "Full time: Defeat. [tg]–[og]."
        else:
            e "Full time: Draw. [tg]–[og]."

        $ perceived = "{:.0f}".format(eval_result["perceived"] * 100)
        e "Your perceived performance: [perceived]%%."

        return
