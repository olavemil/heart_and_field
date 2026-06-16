# Save / load integration (technical §8, reworked in Phase 22A).
#
# Native Ren'Py saves carry engine state as the `fh_save_blob` JSON
# string (see runtime.rpy: fh_checkpoint / after_load). The labels
# below are the legacy explicit path — a persistent-backed slot used
# by the end-of-week "Save and quit" menu. Both serialise the same
# payload via session.serialise().

init python:

    def _fh_save_json(filename="_fh_save"):
        """Serialise engine state to the persistent quick-save slot."""
        data = fh.session.serialise()
        json_str = json.dumps(data, ensure_ascii=False)
        renpy.save_persistent()
        if not hasattr(persistent, "fh_saves"):
            persistent.fh_saves = {}
        persistent.fh_saves[filename] = json_str

    def _fh_load_json(filename="_fh_save"):
        """Deserialise engine state from the persistent quick-save slot."""
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
        loaded_ok = False
        _loaded = _fh_load_json()
        if _loaded is not None:
            fh.session = _loaded
            _loaded = None  # keep the unpicklable session out of the store
            # warm_marquees is idempotent: marquee graphs already on disk
            # keep their existing variants; new authored marquees are
            # picked up on load.
            fh_init_backgrounds()
            fh_checkpoint()
            loaded_ok = True
    if loaded_ok:
        e "Game loaded. Season [fh.session.state.week_phase.season], Week [fh.session.state.week_phase.week]."
        jump week_loop
    else:
        e "No save found."
    return
