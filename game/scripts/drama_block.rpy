# Drama/training/pregame/downtime event block.
#
# A single label that handles any non-game, non-postgame event slot.
# Engine does ALL selection, casting, and resolution; this file only
# displays text and collects the player's branch choice.

label drama_block(slot_index):
    # Ask the engine to pick an event for this slot.
    $ bp = session.select_event_for_slot(slot_index)

    if bp is None:
        e "The day passes quietly."
        return

    # Cast the event.
    $ cast = session.cast_event(bp)
    if cast is None:
        e "Nothing comes of it."
        return

    # Get player-facing choices.
    $ choices = session.get_choices(bp)

    # Show a brief scene intro.
    $ slot = session.schedule.slots[slot_index]
    $ block_label = slot.block_type.value.replace("_", " ").title()
    e "[block_label]"

    if len(choices) == 1:
        # Single outcome — no choice needed.
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
        # Fallback: pick first branch.
        $ branch = list(choices.keys())[0]

    # Resolve the event (mutates engine state).
    $ record = session.resolve_event(bp, branch, cast, slot_index)

    # Narrate the outcome.
    $ narration = session.narrate_outcome(bp, cast, record)
    e "[narration]"

    return
