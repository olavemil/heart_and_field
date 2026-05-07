"""Scene composition helpers — pure logic the Ren'Py composite reads.

Phase 11D's ``scene_compose.rpy`` wraps :func:`variant_crossfade_state`
in a Ren'Py ``DynamicDisplayable`` so the engine math can be tested in
plain Python without standing up a Ren'Py runtime.

The crossfade is *continuous*: with N variants it cycles
``A → B → C → ... → A`` with each transition taking ``fade_seconds``.
There is no hold time on a single variant — the screen is always
interpolating, so the result reads as gentle motion rather than a
hard cut. With a single variant the crossfade collapses to a static
image (``progress = 0``).
"""

from __future__ import annotations


def variant_crossfade_state(
    shown_time: float,
    variant_count: int,
    fade_seconds: float = 1.0,
) -> tuple[int, int, float]:
    """Compute the current crossfade state at ``shown_time`` seconds.

    Returns ``(idx_a, idx_b, progress)`` where:

    - ``idx_a`` is the variant fading *out* (visible at progress=0).
    - ``idx_b`` is the variant fading *in* (visible at progress=1).
    - ``progress`` ∈ [0, 1) is how far through the current 1s
      transition we are.

    With ``variant_count <= 1`` returns ``(0, 0, 0.0)`` so the renderer
    shows the single variant unchanged.
    """
    if variant_count <= 1:
        return 0, 0, 0.0
    if fade_seconds <= 0:
        raise ValueError("fade_seconds must be positive")
    if shown_time < 0:
        # Negative shown_time can occur briefly during transition setup
        # in some Ren'Py paths; clamp rather than raise.
        shown_time = 0.0

    cycle = (shown_time / fade_seconds) % variant_count
    idx_a = int(cycle) % variant_count
    idx_b = (idx_a + 1) % variant_count
    progress = cycle - int(cycle)
    return idx_a, idx_b, progress
