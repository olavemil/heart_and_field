"""Tests for engine.figure_layout — figure composition geometry."""

from engine.figure_layout import (
    CHEST_ANCHOR_PT,
    ENTER_CHEST_Y_FRAC,
    ENTER_HEIGHT_FRAC,
    NPC_BASELINE_FRAC,
    PLAYER_HEIGHT_FRAC,
    FigureDistance,
    FigureSlot,
    compute_layout,
)

W, H = 1280, 720


def _overlap_frac(a, b) -> float:
    """Horizontal overlap as a fraction of the narrower figure's width."""
    inter = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
    if inter <= 0:
        return 0.0
    return inter / min(a.width, b.width)


def _player_npc(**npc):
    return [FigureSlot(role="player"), FigureSlot(role="npc", **npc)]


class TestVerticalBaseline:
    def test_standing_npc_baseline_static_across_distance(self):
        # The NPC's feet sit on the same line regardless of proximity —
        # no vertical bobbing between scenes.
        far = compute_layout(W, H, _player_npc(), distance=FigureDistance.DISTANT)
        near = compute_layout(W, H, _player_npc(), distance=FigureDistance.CLOSE)
        npc_far, npc_near = far[1], near[1]
        assert npc_far.y + npc_far.height == npc_near.y + npc_near.height
        assert npc_far.y + npc_far.height == NPC_BASELINE_FRAC * H

    def test_player_large_left_and_within_top_edge(self):
        boxes = compute_layout(W, H, _player_npc())
        player = boxes[0]
        assert player.cx < 0.35 * W            # left foreground
        assert player.height > H               # larger than canvas
        assert player.y + player.height > H    # feet below the frame
        assert player.y >= 0                   # ~10% downscale: top in frame
        assert PLAYER_HEIGHT_FRAC < 1.1        # downscaled from 1.15


class TestDistance:
    def test_closer_distance_pulls_npc_toward_player(self):
        far = compute_layout(W, H, _player_npc(), distance=FigureDistance.DISTANT)[1]
        near = compute_layout(W, H, _player_npc(), distance=FigureDistance.INTIMATE)[1]
        assert near.cx < far.cx  # closer = smaller x (toward left player)

    def test_distant_npc_is_smaller_than_close(self):
        distant = compute_layout(W, H, _player_npc(), distance=FigureDistance.DISTANT)[1]
        close = compute_layout(W, H, _player_npc(), distance=FigureDistance.CLOSE)[1]
        assert distant.height < close.height  # depth cue via scale

    def test_normal_keeps_heads_visible(self):
        boxes = compute_layout(W, H, _player_npc(), distance=FigureDistance.NORMAL)
        assert _overlap_frac(boxes[0], boxes[1]) <= 0.26  # ~normal cap

    def test_intimate_allows_more_overlap(self):
        normal = compute_layout(W, H, _player_npc(), distance=FigureDistance.NORMAL)
        intimate = compute_layout(W, H, _player_npc(), distance=FigureDistance.INTIMATE)
        ov_normal = _overlap_frac(normal[0], normal[1])
        ov_intimate = _overlap_frac(intimate[0], intimate[1])
        assert ov_intimate > ov_normal
        assert ov_intimate >= 0.4


class TestEnterExit:
    def test_entering_is_downscaled_and_chest_anchored(self):
        boxes = compute_layout(W, H, _player_npc(entering=True))
        npc = boxes[1]
        assert npc.height == ENTER_HEIGHT_FRAC * H          # downscaled
        chest_y = npc.y + CHEST_ANCHOR_PT * npc.height
        assert abs(chest_y - ENTER_CHEST_Y_FRAC * H) < 1e-6  # chest at 1/3

    def test_exiting_uses_same_anchor(self):
        boxes = compute_layout(W, H, _player_npc(exiting=True))
        npc = boxes[1]
        assert npc.height == ENTER_HEIGHT_FRAC * H


class TestMultipleNPCs:
    def test_two_npcs_both_heads_visible(self):
        slots = [
            FigureSlot(role="player"),
            FigureSlot(role="npc"),
            FigureSlot(role="npc"),
        ]
        boxes = compute_layout(W, H, slots, distance=FigureDistance.NORMAL)
        # All three pairwise overlaps within the normal cap.
        assert _overlap_frac(boxes[0], boxes[1]) <= 0.26
        assert _overlap_frac(boxes[1], boxes[2]) <= 0.26
        # Distinct positions.
        assert boxes[1].cx != boxes[2].cx

    def test_npc_only_scene(self):
        boxes = compute_layout(W, H, [FigureSlot(role="npc")])
        assert len(boxes) == 1
        assert boxes[0].y + boxes[0].height == NPC_BASELINE_FRAC * H
