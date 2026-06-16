# Runtime holder + save integration (Phase 22A/22C).
#
# Ren'Py pickles every store variable assigned after init. The engine
# session is not picklable (blueprints carry lambda predicates), so it
# lives on `fh` — an object bound during init, which Ren'Py treats as
# constant and never saves. Engine state instead rides saves as a JSON
# blob (`fh_save_blob`), refreshed at checkpoints and rebuilt in
# `after_load`.

init -1 python:
    import json
    import os
    import time

    class FHRuntime(object):
        """Out-of-store home for unpicklable engine objects.

        `session` is the live GameSession; `bp` is per-event scratch so
        event blocks never bind a blueprint (lambdas!) into the store.
        """

        def __init__(self):
            self.session = None
            self.bp = None

    fh = FHRuntime()

    def fh_checkpoint():
        """Serialise engine state into the saved store blob.

        Called at week start and after each resolved event/match so a
        native Ren'Py save made at any dialogue picks up state no older
        than the start of the in-progress scene.
        """
        if fh.session is not None:
            store.fh_save_blob = json.dumps(
                fh.session.serialise(), ensure_ascii=False
            )

    def fh_choose_branch(choices):
        """Present the player-facing branch menu for any branch count.

        `choices` is {branch_id: label}. A single branch resolves
        without a menu.
        """
        if len(choices) <= 1:
            return next(iter(choices))
        return renpy.display_menu(
            [(label, key) for key, label in choices.items()]
        )

    def fh_init_backgrounds():
        bg_root = os.path.join(config.gamedir, "assets", "backgrounds")
        fh.session.init_backgrounds(
            bg_root,
            comfyui_client=fh.session.comfyui_client,
            warm_marquees=True,
        )


# Engine state for native saves. A plain JSON string — always picklable.
default fh_save_blob = None

# Engine mutations are not rollback-aware; rolling back only desyncs the
# display from the simulation. Re-enable once the engine snapshots state.
define config.rollback_enabled = False


# Ren'Py runs this after any native load: the pickled store (including
# fh_save_blob and slot_idx) is restored, but fh.session is gone — it
# was never saved. Rebuild it from the blob and resume the week loop at
# the current slot rather than at the saved statement, since mid-label
# scratch state (fh.bp, cast) does not survive the load.
label after_load:
    python:
        if fh_save_blob is not None:
            from engine.session import GameSession
            fh.session = GameSession.deserialise(json.loads(fh_save_blob))
            fh_init_backgrounds()
    if fh.session is not None:
        jump week_resume
    return
