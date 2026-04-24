## Field & Heart — game options.

define config.name = _("Field & Heart")
define gui.show_name = True
define config.version = "0.1"

define gui.about = _p("""
Field & Heart — a sports drama simulation.
Engine + narrative by code; Ren'Py is the display shell.
""")

define build.name = "FieldAndHeart"

## Sounds and music

define config.has_sound = True
define config.has_music = True
define config.has_voice = False

## Transitions

define config.enter_transition = dissolve
define config.exit_transition = dissolve
define config.intra_transition = dissolve
define config.after_load_transition = None
define config.end_game_transition = None

## Window management

define config.window = "auto"
define config.window_show_transition = Dissolve(.2)
define config.window_hide_transition = Dissolve(.2)

## Preference defaults

default preferences.text_cps = 0
default preferences.afm_time = 15

## Save directory

define config.save_directory = "FieldAndHeart-1"

## Icon (will use default until we have a custom one)
# define config.window_icon = "gui/window_icon.png"

## Build configuration

init python:
    build.classify('**~', None)
    build.classify('**.bak', None)
    build.classify('**/.**', None)
    build.classify('**/#**', None)
    build.classify('**/thumbs.db', None)

    ## Exclude engine dev files from distribution.
    build.classify('tests/**', None)
    build.classify('notebooks/**', None)
    build.classify('*.egg-info/**', None)
    build.classify('pyproject.toml', None)
    build.classify('CLAUDE.md', None)
    build.classify('IMPLEMENTATION_PLAN.md', None)
    build.classify('.venv/**', None)

    build.documentation('*.html')
    build.documentation('*.txt')
