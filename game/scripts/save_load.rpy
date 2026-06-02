# Save / load integration — hooks Ren'Py's save system to engine
# serialise / deserialise (technical §8).
#
# Ren'Py's built-in save system will capture the `session` variable
# automatically since it's a store variable. But because our engine
# uses numpy arrays and complex dataclasses, we override with explicit
# JSON serialisation.

init python:
    import json

    def _fh_save_json(filename="_fh_save"):
        """Serialise engine state to a Ren'Py save slot."""
        data = session.serialise()
        json_str = json.dumps(data, ensure_ascii=False)
        renpy.save_persistent()
        # Store in persistent for cross-session access.
        if not hasattr(persistent, "fh_saves"):
            persistent.fh_saves = {}
        persistent.fh_saves[filename] = json_str

    def _fh_load_json(filename="_fh_save"):
        """Deserialise engine state from a Ren'Py save slot."""
        if not hasattr(persistent, "fh_saves"):
            return None
        json_str = persistent.fh_saves.get(filename)
        if json_str is None:
            return None
        data = json.loads(json_str)
        return GameSession.deserialise(data)


label save_game:
    python:
        _fh_save_json()
    e "Game saved."
    return


label load_game:
    python:
        renpy.not_infinite_loop(600)
        import os
        loaded = _fh_load_json()
        if loaded is not None:
            session = loaded
            bg_root = os.path.join(config.gamedir, "assets", "backgrounds")
            # warm_marquees is idempotent: marquee graphs already on disk
            # keep their existing variants; new authored marquees are
            # picked up on load.
            session.init_backgrounds(
                bg_root,
                comfyui_client=session.comfyui_client,
                warm_marquees=True,
            )
    if loaded is not None:
        e "Game loaded. Season [session.state.week_phase.season], Week [session.state.week_phase.week]."
        jump week_loop
    else:
        e "No save found."
    return
