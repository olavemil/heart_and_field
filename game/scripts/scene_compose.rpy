# Live scene composite (Phase 11D)
#
# Stacks the engine-driven layers — primary background, noise overlays,
# colour grades — into a single ``scene`` show. Engine calls populate
# the values; ``show_scene_live`` reads them and swaps the displayed
# layers via ``renpy.show`` so each layer can be crossfaded
# independently when conditions change.
#
# No simulation logic lives here — the engine resolves everything; this
# file only orchestrates display.

init python:
    import os
    from engine.scene_compose import variant_crossfade_state

    # Track which overlay tags are currently shown so we can hide stale
    # layers when scene/weather conditions change.
    _scene_live_overlay_tags = set()

    # Figure layer tags currently shown (Phase 23 figure composite).
    _fh_figure_tags = set()

    # How long each variant→next-variant crossfade takes. Continuous —
    # no hold on any single variant — so the result reads as a slight
    # sense of life rather than a discrete cycle.
    SCENE_VARIANT_FADE_SECONDS = 1.0

    # Reasonable default screen dimensions; falls back to Ren'Py's
    # ``config.screen_width`` / ``config.screen_height`` at runtime.
    def _scene_canvas():
        return (
            getattr(config, "screen_width", 1280),
            getattr(config, "screen_height", 720),
        )

    def _fh_image(path):
        """Build a RenPy Image from an engine path.

        The engine returns absolute filesystem paths (manifest.resolve),
        but RenPy's loader resolves image names *relative to game/* and
        searches its file index — an absolute path is never found. Convert
        paths under the game dir to a game-relative, forward-slash name so
        the loader can find them; pass anything else through unchanged.
        """
        p = str(path)
        gamedir = config.gamedir
        try:
            if os.path.isabs(p) and os.path.commonpath([p, gamedir]) == gamedir:
                p = os.path.relpath(p, gamedir).replace(os.sep, "/")
        except ValueError:
            pass  # different drive / not comparable — leave as-is
        return Image(p)

    def _stretched(path, alpha):
        """Show a small grade or overlay PNG stretched to fill the
        canvas at the given alpha. Used by every grade / overlay layer."""
        if path is None:
            return None
        return Transform(
            _fh_image(path),
            xysize=_scene_canvas(),
            alpha=float(alpha),
        )

    def _build_variant_displayable(variant_paths, fade_seconds=None):
        """Build a continuously-crossfading background displayable.

        - 0 variants → ``None`` (caller falls back to nothing).
        - 1 variant → a static ``Image`` (no machinery).
        - 2+ variants → a ``DynamicDisplayable`` cycling through them
          with a ``fade_seconds`` linear crossfade between adjacent
          variants. Loops forever; the scene's ``shown_time`` resets
          when the displayable is re-shown so each scene starts at
          variant 0.
        """
        if not variant_paths:
            return None
        if len(variant_paths) == 1:
            return _fh_image(variant_paths[0])

        fade = fade_seconds if fade_seconds is not None else SCENE_VARIANT_FADE_SECONDS
        canvas = _scene_canvas()
        images = [_fh_image(p) for p in variant_paths]

        def _render(st, at):
            idx_a, idx_b, progress = variant_crossfade_state(
                st, len(images), fade,
            )
            # Bottom layer is the incoming variant fully opaque; top
            # layer is the outgoing variant fading out so the blend
            # totals exactly 1.0 throughout the transition.
            return Composite(
                canvas,
                (0, 0), images[idx_b],
                (0, 0), Transform(images[idx_a], alpha=1.0 - progress),
            ), 1.0 / 30.0  # 30 fps redraw budget

        return DynamicDisplayable(_render)

    def show_scene_live(session, graph_id, node_name):
        """Resolve and display every layer for the given scene.

        Idempotent across calls — re-running with the same args
        regenerates the same composite. Overlay tags are tracked so
        scene transitions properly hide stale layers.
        """
        # Trigger the canonical visit (mark visited, schedule variant
        # promotion, generate primary if needed). The variant list is
        # then read separately so the crossfade builder gets the
        # full set including any already-promoted variants.
        primary = session.scene_path(graph_id, node_name)
        if primary is not None:
            renpy.scene()
            variants = session.scene_variants(graph_id, node_name)
            bg_displayable = (
                _build_variant_displayable(variants)
                or _fh_image(primary)
            )
            renpy.show("scene_bg", what=bg_displayable)

        # Colour grades — three layers stacked at low alpha.
        grades = session.grade_paths()
        if grades is not None:
            time_path, weather_path, mood_path = grades
            renpy.show("grade_time",    what=_stretched(time_path,    0.15))
            renpy.show("grade_weather", what=_stretched(weather_path, 0.12))
            renpy.show("grade_mood",    what=_stretched(mood_path,    0.10))

        # Noise overlays — variable per scene/weather.
        new_tags = set()
        for spec, path in session.overlays_for_scene(graph_id, node_name):
            tag = "ov_" + spec.overlay.value
            new_tags.add(tag)
            renpy.show(tag, what=_stretched(path, spec.alpha))

        # Hide any overlay tags that were shown last time but not now.
        global _scene_live_overlay_tags
        for stale in _scene_live_overlay_tags - new_tags:
            renpy.hide(stale)
        _scene_live_overlay_tags = new_tags

    def show_figures(session, blueprint, cast):
        """Composite the event's figures over the current background.

        The engine resolves which figures and where (figure_layout_for);
        this only places the matted images. Player draws on top (zorder),
        NPCs behind. Idempotent — stale figure tags are hidden. Proximity
        (FigureDistance) defaults to NORMAL until events cue it.
        """
        global _fh_figure_tags
        w, h = _scene_canvas()
        placements = session.figure_layout_for(blueprint, cast, w, h)
        new_tags = set()
        for i, (path, box, role) in enumerate(placements):
            tag = "fh_fig_%d" % i
            new_tags.add(tag)
            d = Transform(
                _fh_image(path),
                xysize=(int(box.width), int(box.height)),
                pos=(int(box.x), int(box.y)),
                anchor=(0, 0),
            )
            renpy.show(tag, what=d, zorder=(70 if role == "player" else 50 + i))
        for stale in _fh_figure_tags - new_tags:
            renpy.hide(stale)
        _fh_figure_tags = new_tags

    def hide_figures():
        """Hide all composited figures (between scenes / before a match)."""
        global _fh_figure_tags
        for tag in _fh_figure_tags:
            renpy.hide(tag)
        _fh_figure_tags = set()

    def hide_scene_live():
        """Tear down every layer the composite owns. Use between events
        when you want a clean slate (e.g. before the match block)."""
        global _scene_live_overlay_tags, _fh_figure_tags
        renpy.scene()
        for tag in _scene_live_overlay_tags:
            renpy.hide(tag)
        _scene_live_overlay_tags = set()
        _fh_figure_tags = set()  # renpy.scene() already cleared them


# --- Status bar overlay -----------------------------------------------------
#
# Reads ``session.clock_display()`` every frame so the time updates
# immediately when an event resolves. During a match the clock swaps to
# the match label per the addendum.

screen status_bar():
    zorder 100
    # Guard: the screen is re-shown on load before the first interaction;
    # fh.session is rebuilt in after_load, but stay safe if it's absent.
    if fh.session is not None:
        $ d = fh.session.clock_display()
        frame:
            align (1.0, 0.0)
            padding (16, 12)
            background "#000000aa"
            vbox:
                spacing 2
                if d.match_label:
                    text d.match_label size 22 color "#ffd"
                else:
                    text "Week [d.week!q] · [d.weekday.value.capitalize()!q]" size 18 color "#dde"
                    text "[d.slot.value.capitalize()!q] · [d.hour_minute!q]" size 22 color "#fff"
                    if d.transition_warning:
                        text "[d.slot.value.capitalize()!q] ending soon" size 12 color "#fc8"
