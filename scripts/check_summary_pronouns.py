"""Validate branch-summary gender handling for one or more event modules.

A summary passes when:
  1. Its raw text contains NO bare gendered pronouns — every pronoun must
     be a role-scoped slot ({they:player}) or neutralised prose.
  2. It resolves cleanly for masculine / feminine / androgynous casts with
     no unresolved [slot] markers left behind.

Usage (run from the repo root):
    .venv/bin/python scripts/check_summary_pronouns.py relationship secret
    .venv/bin/python scripts/check_summary_pronouns.py --all
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "game"))

from engine.characters import CharacterRole, TierBCharacter  # noqa: E402
from engine.narrative import NarrationContext, _substitute  # noqa: E402

# Bare gendered words that must not survive in a raw summary.
_GENDERED = re.compile(
    r"\b(he|him|his|himself|she|her|hers|herself|"
    r"man|woman|lad|lass|boy|girl|guy|gal|"
    r"brother|sister|son|daughter|father|mother|"
    r"his|hers|mr|mrs|ms|sir|madam)\b",
    re.IGNORECASE,
)
_SLOT_LEFTOVER = re.compile(r"\[[a-zA-Z_][\w:]*\]")
# Narration is third-person past tense — second person is a voice error.
_SECOND_PERSON = re.compile(r"\b(you|your|yours|yourself|you'd|you're|you'll)\b", re.IGNORECASE)
# A pronoun slot followed by a plural-only verb breaks for he/she
# ("he were", "she have"). Catch the common be/aux verbs.
_BAD_AGREEMENT = re.compile(
    r"\{[Tt]hey:[a-z_]+\}('?d)?\s+(were|are|have|do|don't|aren't|weren't|haven't)\b"
)

ALL_MODULES = [
    "celebration", "conflict", "downtime", "external_pressure",
    "institutional", "mentor_rival", "personal", "postgame", "pregame",
    "relationship", "romantic", "secret", "sport", "training",
    "vulnerability",
]


def _char(gp: str) -> TierBCharacter:
    c = TierBCharacter(id="x", name="Casey", role=CharacterRole.MIDFIELDER, stats={})
    c.gender_presentation = gp
    return c


def _check_text(
    bp_id: str, label: str, text: str, roles: list[str]
) -> list[tuple[str, str, str, str]]:
    """Run every guard on one authored narration string."""
    problems: list[tuple[str, str, str, str]] = []
    if not text:
        return problems
    hit = _GENDERED.search(text)
    if hit:
        problems.append((bp_id, label, f"gendered word '{hit.group()}'", text))
    sp = _SECOND_PERSON.search(text)
    if sp:
        problems.append(
            (bp_id, label, f"second person '{sp.group()}' (use third person)", text)
        )
    ba = _BAD_AGREEMENT.search(text)
    if ba:
        problems.append(
            (bp_id, label, f"verb agreement '{ba.group()}' breaks for he/she", text)
        )
    for gp in ("masculine", "feminine", "androgynous"):
        cast = {r: _char(gp) for r in roles}
        ctx = NarrationContext(
            target=cast.get("player"), cast=cast, branch_summary=text
        )
        resolved = _substitute(text, ctx)
        leftover = _SLOT_LEFTOVER.search(resolved)
        if leftover:
            problems.append((bp_id, label, f"unresolved {leftover.group()}", resolved))
            break
    return problems


def check_module(modname: str) -> list[tuple[str, str, str, str]]:
    m = importlib.import_module(f"content.events.{modname}")
    problems: list[tuple[str, str, str, str]] = []
    for bp in m.BLUEPRINTS:
        roles = [s.role for s in bp.participants]
        # Pre-choice setup beat (Phase 24B).
        problems += _check_text(bp.id, "setup", bp.setup or "", roles)
        for branch, outcome in bp.outcomes.items():
            # Result beat plus the optional action / reaction beats (24B).
            problems += _check_text(bp.id, branch, outcome.summary or "", roles)
            problems += _check_text(
                bp.id, f"{branch}/action", outcome.action_summary or "", roles
            )
            problems += _check_text(
                bp.id, f"{branch}/reaction", outcome.reaction_summary or "", roles
            )
    return problems


def main() -> int:
    args = sys.argv[1:]
    mods = ALL_MODULES if (not args or args == ["--all"]) else args
    total = 0
    for mod in mods:
        problems = check_module(mod)
        if problems:
            print(f"FAIL {mod}: {len(problems)} issue(s)")
            for bid, branch, why, text in problems:
                print(f"  - {bid} [{branch}] {why}\n      {text[:120]}")
            total += len(problems)
        else:
            print(f"OK   {mod}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
