# Character display and background labels (technical §9).
#
# Ren'Py labels that call CharacterVisual.render() and display the
# result. No rendering logic here — the engine handles everything.
# Swapping prototype → final must not touch this file.

init python:
    from engine.visual import Pose as _FHPose

    # Pose lookup bound at init so label bodies don't import into the
    # pickled store (22A hygiene).
    _FH_POSE_MAP = {p.value: p for p in _FHPose}


label show_character(character, expression=None, intensity=None, mood=0.0, pose_name="standing"):
    # Derive pose enum from string.
    python:
        pose = _FH_POSE_MAP.get(pose_name, _FHPose.STANDING)

        sprite_path = fh.session.visual_manager.render_character(
            character,
            expression=expression,
            intensity=intensity,
            mood=mood,
            pose=pose,
        )

    # Display the sprite.
    if sprite_path:
        show expression sprite_path as character_sprite at center
    return


label hide_character:
    hide character_sprite
    return


label set_background(location):
    python:
        bg_path = fh.session.visual_manager.render_background(location)

    if bg_path:
        scene expression bg_path
    else:
        scene black
    return
