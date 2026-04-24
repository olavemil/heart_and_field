# Character display and background labels (technical §9).
#
# Ren'Py labels that call CharacterVisual.render() and display the
# result. No rendering logic here — the engine handles everything.
# Swapping prototype → final must not touch this file.

label show_character(character, expression=None, intensity=None, mood=0.0, pose_name="standing"):
    # Derive pose enum from string.
    python:
        from engine.visual import Pose, Expression

        pose_map = {p.value: p for p in Pose}
        pose = pose_map.get(pose_name, Pose.STANDING)

        sprite_path = session.visual_manager.render_character(
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
        bg_path = session.visual_manager.render_background(location)

    if bg_path:
        scene expression bg_path
    else:
        scene black
    return
