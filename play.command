#!/bin/sh
# Launch Field & Heart.
#
# Double-click this file in Finder, or run it from a terminal:
#   ./play.command
#
# Finds the Ren'Py SDK (expected at ./renpy-8.5.2-sdk, falling back to
# the main checkout when run from a git worktree) and starts the game
# directly — no launcher UI, no manual SDK paths.

cd "$(dirname "$0")" || exit 1
root="$(pwd)"

sdk="${RENPY_SDK:-$root/renpy-8.5.2-sdk}"
if [ ! -x "$sdk/renpy.sh" ] && [ -x "$HOME/Git/heart_and_field/renpy-8.5.2-sdk/renpy.sh" ]; then
    sdk="$HOME/Git/heart_and_field/renpy-8.5.2-sdk"
fi

if [ ! -x "$sdk/renpy.sh" ]; then
    echo "Ren'Py SDK not found at $root/renpy-8.5.2-sdk."
    echo "Download the SDK from https://renpy.org and unpack it there,"
    echo "or point at it directly: RENPY_SDK=/path/to/sdk ./play.command"
    exit 1
fi

exec "$sdk/renpy.sh" "$root"
