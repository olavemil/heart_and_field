"""Phase 22D: authored ChoiceNode labels on every multi-branch blueprint.

Without a ChoiceNode, `GameSession.get_choices` falls back to
title-casing branch ids ("Escalate" / "Defuse") and the player chooses
blind. These tests enforce that every blueprint with two or more
outcome branches carries an authored choice with intent-voiced labels,
and that the option keys stay in lockstep with the outcome branches
(a mismatch would KeyError at resolve time).
"""

from pathlib import Path

from engine.content_loader import load_blueprints_from_path

CONTENT_ROOT = Path(__file__).resolve().parents[1] / "game" / "content"


def _authored_blueprints():
    return load_blueprints_from_path(CONTENT_ROOT / "events")


def _choice_for(bp):
    return next((b.choice for b in bp.blocks if b.choice is not None), None)


def test_every_multibranch_blueprint_has_choice_node():
    missing = [
        bp.id
        for bp in _authored_blueprints()
        if len(bp.outcomes) >= 2 and _choice_for(bp) is None
    ]
    assert missing == [], f"blueprints without authored choices: {missing}"


def test_choice_options_match_outcome_branches():
    mismatched = []
    for bp in _authored_blueprints():
        choice = _choice_for(bp)
        if choice is None:
            continue
        if set(choice.options) != set(bp.outcomes):
            mismatched.append(
                (bp.id, sorted(choice.options), sorted(bp.outcomes))
            )
    assert mismatched == [], f"option/outcome key mismatches: {mismatched}"


def test_choice_labels_are_authored_text():
    """Labels must be real text, not echoes of the branch id."""
    weak = []
    for bp in _authored_blueprints():
        choice = _choice_for(bp)
        if choice is None:
            continue
        if not choice.prompt.strip():
            weak.append((bp.id, "<empty prompt>"))
        for branch, label in choice.options.items():
            if not label.strip():
                weak.append((bp.id, branch))
            elif label.strip().lower() == branch.replace("_", " ").lower():
                weak.append((bp.id, branch))
    assert weak == [], f"empty or id-echo labels: {weak}"
