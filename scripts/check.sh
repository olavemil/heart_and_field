#!/bin/sh
# Regression gate: pytest (engine) + Ren'Py lint (.rpy layer).
#
# pytest cannot see .rpy parse errors or undefined-name regressions —
# both stale error logs (errors.txt, traceback.txt) were exactly that.
# Run this before committing changes that touch game/scripts/.
#
# Usage: scripts/check.sh [path-to-renpy-sdk]

set -e

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
main_root="$HOME/Git/heart_and_field"

# Worktrees don't carry the gitignored SDK / venv — fall back to the
# main checkout for both.
sdk="${1:-$repo_root/renpy-8.5.2-sdk}"
if [ ! -x "$sdk/renpy.sh" ] && [ -x "$main_root/renpy-8.5.2-sdk/renpy.sh" ]; then
    sdk="$main_root/renpy-8.5.2-sdk"
fi
py="$repo_root/.venv/bin/python"
if [ ! -x "$py" ] && [ -x "$main_root/.venv/bin/python" ]; then
    py="$main_root/.venv/bin/python"
fi

echo "== pytest =="
"$py" -m pytest "$repo_root/tests" -q

if [ -x "$sdk/renpy.sh" ]; then
    echo "== renpy lint =="
    "$sdk/renpy.sh" "$repo_root" lint
else
    echo "== renpy lint skipped (no SDK at $sdk) =="
fi
