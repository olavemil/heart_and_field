"""Contextual continuation — state-vector perturbation (ADR-002, Phase 25.4).

Given the prior event's resolved axes ``(domain, nature, tone, location)``,
decide which axes **drift** to form the next event's target. Continuity
comes from the axes that *hold*; variation from the few that *change*.

No adjacency tables: a drifting axis simply takes a different value (the
selection step then favours blueprints near the target); the *kept* axes
carry the through-line, so the sequence reads as a gradual drift —
e.g. hold (domain, nature), drift tone; next hold (domain, tone), drift
nature; and so on.

**Drift count is a continuity-biased cascade** (the algorithm sketched for
this): axes are considered in random order; each drifts with probability
``3 / (4 + 2 * changes)`` where ``changes`` counts drifts so far (including
any the outcome already forced). The cascade **stops at the first axis
that holds**, so each further drift is progressively less likely.

Stopping on the first hold is deliberate: it is what gives ~25% no-drift
and a 0-2-change mode. Checking *every* axis instead would drift almost
always (a held axis doesn't raise the counter, so the next still rolls
0.75 → P(no drift) ≈ 0.25**4 ≈ 0.4%).

Resulting distribution over change-count (no forced drift, 4 axes):

    0: 25.0%   1: 37.5%   2: 23.4%   3: 9.8%   4: 4.2%

(mean ≈ 1.3) — mostly one or two axes move, occasionally a more dramatic
scene shift, rarely none.

Arc / scheduled events are handled *above* this: a chained or
outcome-scheduled event is respected directly (its own vector), bypassing
perturbation. This module only produces the *contextual* drift target.
"""

from __future__ import annotations

import random as _random

# The drifting axes. ``time`` is not drifted directly — it advances as a
# consequence of the others (a domain/location change books travel time).
CONTINUATION_AXES: tuple[str, ...] = ("domain", "nature", "tone", "location")

# Cascade tuning: P(drift) = DRIFT_NUM / (DRIFT_BASE + DRIFT_STEP * changes).
DRIFT_NUM = 3.0
DRIFT_BASE = 4.0
DRIFT_STEP = 2.0


def drift_probability(changes: int) -> float:
    """P(the next considered axis drifts), given ``changes`` so far."""
    return DRIFT_NUM / (DRIFT_BASE + DRIFT_STEP * changes)


# Axes the contextual *selection* bias scores today. tone is owned by the
# resolver (`resolve_event_tone`); location lands with its own slice
# (needs the prior event's location on the record). So selection drifts
# the blueprint-identifying structural axes.
CONTEXTUAL_AXES: tuple[str, ...] = ("domain", "nature")

# Max selection boost for a candidate fully on the drift target.
CONTEXTUAL_GAIN = 1.6


def prior_essence(outcome_log) -> "tuple | None":
    """The ``(domain, nature)`` of the most recent outcome that carried an
    ``EventType`` — the anchor the next event drifts from. ``None`` when
    no prior typed event exists (e.g. the first event)."""
    for record in reversed(outcome_log):
        tid = getattr(record, "taxonomy_id", None)
        if tid is not None:
            return (tid.domain, tid.nature)
    return None


def contextual_bias(
    event_type,
    *,
    prior,
    drifted: set[str],
    gain: float = CONTEXTUAL_GAIN,
) -> float:
    """Selection multiplier favouring candidates that match the drift
    target: a **held** axis should equal the prior value, a **drifted**
    axis should differ. Soft (∈ ``[1, 1+gain]``) so non-target candidates
    stay selectable when the exact target is unauthored. ``1.0`` when there
    is no prior or no event type.
    """
    if prior is None or event_type is None:
        return 1.0
    prior_domain, prior_nature = prior
    axis_vals = {
        "domain": (event_type.domain, prior_domain),
        "nature": (event_type.nature, prior_nature),
    }
    hits = sum(
        1
        for axis in CONTEXTUAL_AXES
        if (axis_vals[axis][0] == axis_vals[axis][1]) != (axis in drifted)
    )
    return 1.0 + gain * (hits / len(CONTEXTUAL_AXES))


def drift_axes(
    rng: _random.Random,
    *,
    axes: tuple[str, ...] = CONTINUATION_AXES,
    forced_changes: int = 0,
) -> set[str]:
    """Decide which axes drift this step (the continuity-biased cascade).

    ``forced_changes`` pre-counts drifts the outcome already imposed (an
    immediate outcome can push an axis — e.g. a ``result_tone`` shift — so
    that drift is in effect before the cascade and raises the bar for
    further change). Returns the set of axes (from ``axes``) that drift;
    the rest hold. Deterministic for a given ``rng`` state.
    """
    order = list(axes)
    rng.shuffle(order)
    changes = forced_changes
    drifted: set[str] = set()
    for axis in order:
        if rng.random() < drift_probability(changes):
            drifted.add(axis)
            changes += 1
        else:
            break  # first hold ends the streak — continuity bias
    return drifted
