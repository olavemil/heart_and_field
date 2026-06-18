# Postgame event block.
#
# Runs after the match. Same flow as drama_block but with access
# to match evaluation data for richer narration context.

label postgame_block(slot_index):
    $ fh.bp = fh.session.select_event_for_slot(slot_index)

    if fh.bp is None:
        e "The changing room empties in silence."
        return

    $ cast = fh.session.cast_event(fh.bp)
    if cast is None:
        e "Everyone drifts off alone."
        return

    # Resolve the background, if this event has a location cue.
    $ scene_info = fh.session.resolve_scene(fh.bp, cast)
    if scene_info is not None:
        $ show_scene_live(fh.session, scene_info[0], scene_info[1])

    # Composite the event's figures over the background (Phase 23).
    $ show_figures(fh.session, fh.bp, cast)

    $ intro = fh.session.scene_intro(fh.bp, cast)
    if intro:
        e "[intro]"
    else:
        e "After the match."

    # Pre-choice premise beat (Phase 24B); empty when unauthored.
    $ setup_pages = fh.session.narrate_setup(fh.bp, cast)
    python:
        for page in setup_pages:
            renpy.say(e, page)

    # Arc recap (Phase 24C): bridge a storyline resumed after a day gap.
    $ recap_pages = fh.session.narrate_arc_recap(fh.bp, cast)
    python:
        for page in recap_pages:
            renpy.say(e, page)

    $ branch = fh_choose_branch(fh.session.get_choices(fh.bp))

    $ record = fh.session.resolve_event(fh.bp, branch, cast, slot_index)
    $ fh_checkpoint()

    # Resolution as ordered beats: action -> reaction -> result (24B).
    $ beats = fh.session.narrate_event(fh.bp, cast, record)
    python:
        for beat in beats:
            for page in beat.pages:
                renpy.say(e, page)

    # Scene boundary: compress the event's prose into the journal (24A).
    $ fh.session.close_scene(cast)

    if scene_info is not None:
        python:
            cue = fh.bp.location
            close = cue is not None and cue.graph_id is None
            fh.session.release_scene(scene_info[0], close=close)

    $ hide_figures()

    $ fh.session.drain_background_prefetch(max_items=2)
    $ fh.bp = None

    return
