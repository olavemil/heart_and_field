# Drama/training/pregame/downtime event block.
#
# A single label that handles any non-game, non-postgame event slot.
# Engine does ALL selection, casting, and resolution; this file only
# displays text and collects the player's branch choice.
#
# The blueprint lives on fh.bp (never the store — blueprints carry
# lambdas and would break native saves; see runtime.rpy).

label drama_block(slot_index):
    # Ask the engine to pick an event for this slot.
    $ fh.bp = fh.session.select_event_for_slot(slot_index)

    if fh.bp is None:
        e "The day passes quietly."
        return

    # Cast the event.
    $ cast = fh.session.cast_event(fh.bp)
    if cast is None:
        e "Nothing comes of it."
        return

    # Resolve the player's stance for this event once (Phase 24C). The
    # figure framing, scene-intro perspective, and the outcome record all
    # read the cached result so they agree.
    $ fh.session.resolve_player_stance(fh.bp, cast)

    # Resolve the background, if this event has a location cue. The
    # composite stacks the primary background, weather/mood/time
    # grades, and per-scene noise overlays so the scene reads as
    # alive without further .rpy plumbing.
    $ scene_info = fh.session.resolve_scene(fh.bp, cast)
    if scene_info is not None:
        $ show_scene_live(fh.session, scene_info[0], scene_info[1])

    # Composite the event's figures over the background (Phase 23):
    # player anchor + interlocutor(s), selected by descriptor + tone.
    $ show_figures(fh.session, fh.bp, cast)

    # Engine-built scene intro: place, company, atmosphere (Phase 22D).
    $ intro = fh.session.scene_intro(fh.bp, cast)
    if intro:
        e "[intro]"

    # Pre-choice premise beat, on its own screen(s) (Phase 24B). Empty
    # when the blueprint authors no setup beyond the intro line.
    $ setup_pages = fh.session.narrate_setup(fh.bp, cast)
    python:
        for page in setup_pages:
            renpy.say(e, page)

    # Arc recap (Phase 24C): if this event resumes a storyline whose last
    # beat was on an earlier day, remind the player before they choose.
    $ recap_pages = fh.session.narrate_arc_recap(fh.bp, cast)
    python:
        for page in recap_pages:
            renpy.say(e, page)

    # Player-facing branch choice (any branch count).
    $ branch = fh_choose_branch(fh.session.get_choices(fh.bp))

    # Resolve the event (mutates engine state).
    $ record = fh.session.resolve_event(fh.bp, branch, cast, slot_index)
    $ fh_checkpoint()

    # Narrate the resolution as ordered beats: action -> reaction ->
    # result, each on its own screen(s) (Phase 24B). Unauthored optional
    # beats are simply absent; the result beat always plays.
    $ beats = fh.session.narrate_event(fh.bp, cast, record)
    python:
        for beat in beats:
            for page in beat.pages:
                renpy.say(e, page)

    # Scene boundary: compress this event's prose into a one-paragraph
    # journal summary so the next scene continues from it (Phase 24A).
    $ fh.session.close_scene(cast)

    # Reap any prefetched-but-unvisited backgrounds. Ad-hoc graphs close;
    # marquee graphs (graph_id authored on the cue) stay open across events.
    if scene_info is not None:
        python:
            cue = fh.bp.location
            close = cue is not None and cue.graph_id is None
            fh.session.release_scene(scene_info[0], close=close)

    $ hide_figures()

    # Drain a few prefetch jobs while the player reads — keeps the
    # background generator warm without blocking.
    $ fh.session.drain_background_prefetch(max_items=2)
    $ fh.bp = None

    return
