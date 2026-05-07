# Postgame event block.
#
# Runs after the match. Same flow as drama_block but with access
# to match evaluation data for richer narration context.

label postgame_block(slot_index):
    $ bp = session.select_event_for_slot(slot_index)

    if bp is None:
        e "The changing room empties in silence."
        return

    $ cast = session.cast_event(bp)
    if cast is None:
        e "Everyone drifts off alone."
        return

    # Resolve the background, if this event has a location cue.
    $ scene_info = session.resolve_scene(bp, cast)
    if scene_info is not None:
        $ show_scene_live(session, scene_info[0], scene_info[1])

    $ choices = session.get_choices(bp)

    e "After the match"

    if len(choices) == 1:
        $ branch = list(choices.keys())[0]
    elif len(choices) == 2:
        $ choice_keys = list(choices.keys())
        $ choice_labels = list(choices.values())
        menu:
            "[choice_labels[0]]":
                $ branch = choice_keys[0]
            "[choice_labels[1]]":
                $ branch = choice_keys[1]
    elif len(choices) == 3:
        $ choice_keys = list(choices.keys())
        $ choice_labels = list(choices.values())
        menu:
            "[choice_labels[0]]":
                $ branch = choice_keys[0]
            "[choice_labels[1]]":
                $ branch = choice_keys[1]
            "[choice_labels[2]]":
                $ branch = choice_keys[2]
    else:
        $ branch = list(choices.keys())[0]

    $ record = session.resolve_event(bp, branch, cast, slot_index)

    $ pages = session.narrate_outcome(bp, cast, record)
    python:
        for page in pages:
            renpy.say(e, page)

    if scene_info is not None:
        python:
            cue = bp.location
            close = cue is not None and cue.graph_id is None
            session.release_scene(scene_info[0], close=close)

    $ session.drain_background_prefetch(max_items=2)

    return
