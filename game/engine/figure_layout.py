"""Figure composition layout (Phase 23 figure layer).

Pure geometry: given a canvas and the figures in a scene, compute each
one's on-screen box. Ren'Py reads the boxes and places the matted
images — no display logic here.

Design constraints (authored):

- **Horizontal position is dynamic** — figures can sit closer / further
  apart (a ``closeness`` knob, animated across scene changes by Ren'Py).
  Overlap is capped so heads stay visible: ~25% normally, up to ~75% for
  an intimate scene.
- **Vertical baseline is static** — standing figures are anchored at the
  same bottom line every frame, so nobody bobs between scenes.
- **Enter/exit downscale** — a figure flagged entering/exiting is drawn
  smaller and anchored by the **chest at 1/3 from the top** (a distant
  approaching/departing figure), rather than feet-on-baseline.

The player is a foreground anchor (large, one side, cropped below the
frame); NPCs sit mid-ground facing the player.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

DEFAULT_ASPECT = 832 / 1216  # matted figure portrait w/h (~0.684)

# Standing figures (fractions of canvas height / width). Heights are the
# ~10%-downscaled baseline (figures were reading too large; the player
# clipped the top edge).
PLAYER_HEIGHT_FRAC = 1.04      # large; just cropped below the frame
PLAYER_CX_FRAC = 0.20          # foreground, left
PLAYER_BASELINE_FRAC = 1.06    # feet below the bottom edge (cropped)
NPC_HEIGHT_FRAC = 0.74         # at NORMAL distance; scaled by FigureDistance
NPC_BASELINE_FRAC = 1.0        # feet at the bottom edge — static baseline
# NPC desired horizontal band, by closeness (0 = far apart, 1 = close).
# NEAR sits inside the normal overlap cap, so at high closeness the cap
# pushes the NPC back (heads visible) unless the distance relaxes it.
NPC_FAR_CX_FRAC = 0.70
NPC_NEAR_CX_FRAC = 0.42

# Enter/exit: smaller, chest anchored at 1/3 from the top.
ENTER_HEIGHT_FRAC = 0.50
ENTER_CHEST_Y_FRAC = 1 / 3     # chest sits this far down the canvas
CHEST_ANCHOR_PT = 0.30         # chest is ~30% down the figure from its top


class FigureDistance(str, Enum):
    """Proximity of the NPC(s) to the player — named levels events cue.

    Drives NPC scale (apparent depth), horizontal closeness, and the
    head-visibility overlap cap together.
    """

    INTIMATE = "intimate"
    CLOSE = "close"
    NORMAL = "normal"
    DISTANT = "distant"


class PlayerFraming(str, Enum):
    """How present the player silhouette is in the frame (Phase 24C).

    Driven by the event's player stance: an actor/reactor owns the
    foreground; an onlooker sits aside; a spectator is pushed small and
    to the edge — the player is in the scene without dominating it.
    """

    FOREGROUND = "foreground"   # actor / reactor — large foreground anchor
    ASIDE = "aside"             # onlooker — present but to the edge, smaller
    BACKGROUND = "background"   # spectator — small, far aside, watching


# Per-framing: player height multiplier (vs PLAYER_HEIGHT_FRAC) and the
# center-x fraction. FOREGROUND reproduces the original anchor exactly.
_PLAYER_FRAMING_PARAMS: dict[PlayerFraming, tuple[float, float]] = {
    PlayerFraming.FOREGROUND: (1.00, PLAYER_CX_FRAC),
    PlayerFraming.ASIDE:      (0.82, 0.12),
    PlayerFraming.BACKGROUND: (0.66, 0.07),
}


# Per-distance: NPC height multiplier (vs NPC_HEIGHT_FRAC), horizontal
# closeness [0,1], and overlap cap (intersection / narrower width).
_DISTANCE_PARAMS: dict[FigureDistance, tuple[float, float, float]] = {
    FigureDistance.INTIMATE: (1.12, 1.00, 0.72),
    FigureDistance.CLOSE:    (1.05, 0.78, 0.40),
    FigureDistance.NORMAL:   (1.00, 0.50, 0.25),
    FigureDistance.DISTANT:  (0.82, 0.22, 0.12),
}


@dataclass(frozen=True)
class FigureSlot:
    role: str = "npc"               # "player" | "npc"
    aspect: float = DEFAULT_ASPECT  # matted image w/h
    entering: bool = False
    exiting: bool = False


@dataclass(frozen=True)
class FigureBox:
    """Top-left placement + size in pixels — Ren'Py resizes the matted
    image to (width, height) and shows it at (x, y)."""

    x: float
    y: float
    width: float
    height: float

    @property
    def cx(self) -> float:
        return self.x + self.width / 2


def _box(cx: float, anchor_y: float, height: float, anchor_pt: float,
         aspect: float) -> FigureBox:
    """Build a box from a center-x, the canvas y its anchor point sits at,
    the figure height, and which fraction down the figure the anchor is
    (1.0 = feet/bottom, ~0.30 = chest)."""
    width = height * aspect
    return FigureBox(
        x=cx - width / 2,
        y=anchor_y - anchor_pt * height,
        width=width,
        height=height,
    )


def _min_center_distance(w_a: float, w_b: float, overlap_cap: float) -> float:
    """Smallest |cx_a - cx_b| keeping overlap ≤ cap·min(width)."""
    return (w_a + w_b) / 2 - overlap_cap * min(w_a, w_b)


def compute_layout(
    canvas_w: int,
    canvas_h: int,
    slots: list[FigureSlot],
    *,
    distance: FigureDistance = FigureDistance.NORMAL,
    player_framing: PlayerFraming = PlayerFraming.FOREGROUND,
) -> list[FigureBox]:
    """Lay out the scene's figures. Returns one box per slot, in order.

    ``distance`` (INTIMATE / CLOSE / NORMAL / DISTANT) sets NPC scale,
    horizontal closeness, and the overlap cap together.

    ``player_framing`` sets how present the player silhouette is —
    FOREGROUND (default, the original anchor) for an actor; ASIDE /
    BACKGROUND shrink it and push it toward the edge for an onlooker /
    spectator (Phase 24C).
    """
    npc_scale, closeness, cap = _DISTANCE_PARAMS[distance]
    npc_height_frac = NPC_HEIGHT_FRAC * npc_scale
    player_h_mult, player_cx_frac = _PLAYER_FRAMING_PARAMS[player_framing]
    W, H = canvas_w, canvas_h

    boxes: list[FigureBox | None] = [None] * len(slots)

    # Player anchor first (foreground slot; framing sets size + position).
    player_box: FigureBox | None = None
    for i, s in enumerate(slots):
        if s.role == "player":
            player_box = _box(
                player_cx_frac * W, PLAYER_BASELINE_FRAC * H,
                PLAYER_HEIGHT_FRAC * player_h_mult * H, 1.0, s.aspect,
            )
            boxes[i] = player_box
            break

    # NPCs distributed across the band right of the player.
    npc_idxs = [i for i, s in enumerate(slots) if s.role != "player"]
    n = len(npc_idxs)
    for k, i in enumerate(npc_idxs):
        s = slots[i]
        if s.entering or s.exiting:
            # Distant approaching/departing figure: small, chest-anchored.
            cx = (NPC_FAR_CX_FRAC if n == 1 else (0.55 + 0.18 * k)) * W
            boxes[i] = _box(
                cx, ENTER_CHEST_Y_FRAC * H, ENTER_HEIGHT_FRAC * H,
                CHEST_ANCHOR_PT, s.aspect,
            )
            continue
        # Standing NPC on the static baseline.
        far, near = NPC_FAR_CX_FRAC, NPC_NEAR_CX_FRAC
        if n == 1:
            cx_frac = far - (far - near) * closeness
        else:
            # Spread n NPCs across [near-ish, far]; closeness compresses
            # the spread toward the centre.
            span = (far - near) * (1.0 - 0.5 * closeness)
            start = (far + near) / 2 - span / 2
            cx_frac = start + span * (k / (n - 1)) if n > 1 else far
        cx = cx_frac * W
        boxes[i] = _box(
            cx, NPC_BASELINE_FRAC * H, npc_height_frac * H, 1.0, s.aspect,
        )

    # Enforce overlap caps left-to-right against the player and prior NPCs,
    # pushing standing figures rightward when too close. Entering/exiting
    # figures are exempt (they're meant to be distant/overlapping).
    placed: list[FigureBox] = []
    if player_box is not None:
        placed.append(player_box)
    order = sorted(
        npc_idxs,
        key=lambda i: boxes[i].cx if boxes[i] else 0.0,
    )
    for i in order:
        s = slots[i]
        b = boxes[i]
        if b is None or s.entering or s.exiting:
            continue
        cx = b.cx
        for other in placed:
            need = _min_center_distance(b.width, other.width, cap)
            if cx - other.cx < need:
                cx = other.cx + need
        if cx != b.cx:
            b = _box(cx, NPC_BASELINE_FRAC * H, b.height, 1.0, s.aspect)
            boxes[i] = b
        placed.append(b)

    return [b for b in boxes if b is not None]
