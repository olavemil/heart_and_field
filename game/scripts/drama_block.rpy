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

    # Resolve the background, if this event has a location cue. The
    # composite stacks the primary background, weather/mood/time
    # grades, and per-scene noise overlays so the scene reads as
    # alive without further .rpy plumbing.
    $ scene_info = fh.session.resolve_scene(fh.bp, cast)
    if scene_info is not None:
        $ show_scene_live(fh.session, scene_info[0], scene_info[1])

    # Put the focal cast member on screen (Phase 22D).
    $ focal = fh.session.focal_character(cast)
    if focal is not None:
        call show_character(focal, mood=fh.session.team_morale) from _call_show_focal_drama

    # Engine-built scene intro: place, company, atmosphere (Phase 22D).
    $ intro = fh.session.scene_intro(fh.bp, cast)
    if intro:
        e "[intro]"

    # Player-facing branch choice (any branch count).
    $ branch = fh_choose_branch(fh.session.get_choices(fh.bp))

    # Resolve the event (mutates engine state).
    $ record = fh.session.resolve_event(fh.bp, branch, cast, slot_index)
    $ fh_checkpoint()

    # Narrate the outcome.
    $ pages = fh.session.narrate_outcome(fh.bp, cast, record)
    python:
        for page in pages:
            renpy.say(e, page)

    # Reap any prefetched-but-unvisited backgrounds. Ad-hoc graphs close;
    # marquee graphs (graph_id authored on the cue) stay open across events.
    if scene_info is not None:
        python:
            cue = fh.bp.location
            close = cue is not None and cue.graph_id is None
            fh.session.release_scene(scene_info[0], close=close)

    if focal is not None:
        hide character_sprite

    # Drain a few prefetch jobs while the player reads — keeps the
    # background generator warm without blocking.
    $ fh.session.drain_background_prefetch(max_items=2)
    $ fh.bp = None

    return
