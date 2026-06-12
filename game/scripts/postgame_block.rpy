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

    # Focal cast member + engine-built scene intro (Phase 22D).
    $ focal = fh.session.focal_character(cast)
    if focal is not None:
        call show_character(focal, mood=fh.session.team_morale) from _call_show_focal_postgame

    $ intro = fh.session.scene_intro(fh.bp, cast)
    if intro:
        e "[intro]"
    else:
        e "After the match."

    $ branch = fh_choose_branch(fh.session.get_choices(fh.bp))

    $ record = fh.session.resolve_event(fh.bp, branch, cast, slot_index)
    $ fh_checkpoint()

    $ pages = fh.session.narrate_outcome(fh.bp, cast, record)
    python:
        for page in pages:
            renpy.say(e, page)

    if scene_info is not None:
        python:
            cue = fh.bp.location
            close = cue is not None and cue.graph_id is None
            fh.session.release_scene(scene_info[0], close=close)

    if focal is not None:
        hide character_sprite

    $ fh.session.drain_background_prefetch(max_items=2)
    $ fh.bp = None

    return
