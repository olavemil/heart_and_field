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

    from engine.session import GameSession
    from engine.schedule import BlockType

define e = Character("Narrator", color="#c8ffc8")


# --- New game ---------------------------------------------------------------

label start:
    $ session = GameSession.new_game("Alex Morgan", seed=42)

    # Create a minimal roster so events can cast.
    python:
        from engine.characters import TierBCharacter, CharacterRole
        from engine.stats import StatName

        roster = {
            "tm_jordan": TierBCharacter(
                id="tm_jordan", name="Jordan Lee",
                role=CharacterRole.MIDFIELDER,
                stats={
                    StatName.STAMINA: 0.7, StatName.COLLABORATION: 0.6,
                    StatName.LEADERSHIP: 0.5, StatName.SPEED: 0.6,
                    StatName.STRENGTH: 0.5, StatName.FINESSE: 0.6,
                    StatName.CONFIDENCE: 0.5, StatName.MOTIVATION: 0.6,
                },
            ),
            "tm_sam": TierBCharacter(
                id="tm_sam", name="Sam Carter",
                role=CharacterRole.DEFENDER,
                stats={
                    StatName.STAMINA: 0.7, StatName.STRENGTH: 0.7,
                    StatName.SPEED: 0.5, StatName.FINESSE: 0.4,
                    StatName.COLLABORATION: 0.6, StatName.CAUTIOUSNESS: 0.7,
                    StatName.CONFIDENCE: 0.5, StatName.MOTIVATION: 0.5,
                },
            ),
            "coach_williams": TierBCharacter(
                id="coach_williams", name="Coach Williams",
                role=CharacterRole.MANAGER,
                stats={
                    StatName.LEADERSHIP: 0.9, StatName.MOTIVATION: 0.7,
                },
            ),
        }
        for cid, char in roster.items():
            session.state.characters[cid] = char

    e "Welcome to Field & Heart."
    e "Season [session.state.week_phase.season], Week [session.state.week_phase.week]."

    jump week_loop


# --- Week loop ---------------------------------------------------------------

label week_loop:
    $ schedule = session.start_week()
    e "A new week begins."

    # Process each slot in order.
    $ slot_idx = 0

    label .next_slot:
        if slot_idx >= len(schedule.slots):
            jump week_end

        $ slot = schedule.slots[slot_idx]

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


# --- End of week -------------------------------------------------------------

label week_end:
    e "End of week [session.state.week_phase.week]."

    menu:
        "Continue to next week":
            $ session.advance_week()
            jump week_loop

        "Save and quit":
            call save_game from _call_save
            return
