"""Tests for engine.visual — character rendering and expression overlays."""

from pathlib import Path

from PIL import Image

from engine.characters import (
    CharacterRole,
    Disposition,
    TierACharacter,
    TierBCharacter,
    TierDSeed,
)
from engine.stats import ObservableName, StatName, StatTuple
from engine.visual import (
    CharacterVisual,
    Expression,
    FaceGenerationSpec,
    Pose,
    SpriteLayer,
    TeamPalette,
    VisualManager,
    apply_overlay,
    expression_from_character,
    generate_placeholder_face,
    get_background,
    procedural_layers,
    select_layers,
)


def _tier_a(
    confidence: float = 0.5,
    insecurity: float = 0.3,
    aggressiveness: float = 0.3,
    collaboration: float = 0.5,
) -> TierACharacter:
    return TierACharacter(
        id="test_player",
        name="Test Player",
        role=CharacterRole.STRIKER,
        stats={
            StatName.CONFIDENCE: StatTuple(value=confidence),
            StatName.INSECURITY: StatTuple(value=insecurity),
            StatName.AGGRESSIVENESS: StatTuple(value=aggressiveness),
            StatName.CAUTIOUSNESS: StatTuple(value=0.4),
            StatName.INTROSPECTION: StatTuple(value=0.5),
            StatName.REFLECTION: StatTuple(value=0.5),
            StatName.COLLABORATION: StatTuple(value=collaboration),
            StatName.DEFENSIVENESS: StatTuple(value=0.2),
            StatName.LEADERSHIP: StatTuple(value=0.5),
            StatName.STAMINA: StatTuple(value=0.6),
            StatName.MOTIVATION: StatTuple(value=0.5),
            StatName.STRENGTH: StatTuple(value=0.5),
            StatName.SPEED: StatTuple(value=0.5),
            StatName.FINESSE: StatTuple(value=0.5),
        },
    )


class TestExpressionMapping:
    def test_neutral_for_tier_d(self):
        seed = TierDSeed(
            role=CharacterRole.STRIKER, skill_rating=0.6
        )
        expr, intensity = expression_from_character(seed)
        assert expr == Expression.NEUTRAL
        assert intensity == 0.5

    def test_high_confidence_yields_confident_or_smug(self):
        char = _tier_a(confidence=0.9, insecurity=0.1)
        expr, intensity = expression_from_character(char)
        # High confidence + low insecurity → SMUG (arrogance) or CONFIDENT (charisma)
        assert expr in (Expression.SMUG, Expression.CONFIDENT, Expression.WARM)
        assert intensity > 0.3

    def test_low_mood_overrides_to_anxious(self):
        char = _tier_a(confidence=0.3, insecurity=0.6)
        expr, intensity = expression_from_character(char, mood=-0.5)
        assert expr == Expression.ANXIOUS

    def test_intensity_is_clamped(self):
        char = _tier_a(confidence=0.9)
        _, intensity = expression_from_character(char)
        assert 0.0 <= intensity <= 1.0

    def test_tier_b_works(self):
        char = TierBCharacter(
            id="npc1",
            name="NPC One",
            role=CharacterRole.MIDFIELDER,
            stats={
                StatName.CONFIDENCE: 0.8,
                StatName.INSECURITY: 0.2,
                StatName.AGGRESSIVENESS: 0.3,
                StatName.CAUTIOUSNESS: 0.5,
                StatName.INTROSPECTION: 0.4,
                StatName.REFLECTION: 0.4,
                StatName.COLLABORATION: 0.6,
                StatName.DEFENSIVENESS: 0.2,
                StatName.LEADERSHIP: 0.5,
                StatName.STAMINA: 0.6,
                StatName.MOTIVATION: 0.5,
                StatName.STRENGTH: 0.5,
            },
        )
        expr, intensity = expression_from_character(char)
        assert isinstance(expr, Expression)
        assert 0.0 <= intensity <= 1.0


class TestFaceGenerationSpec:
    def test_seed_from_id_deterministic(self):
        s1 = FaceGenerationSpec.seed_from_id("player")
        s2 = FaceGenerationSpec.seed_from_id("player")
        assert s1 == s2

    def test_different_ids_different_seeds(self):
        s1 = FaceGenerationSpec.seed_from_id("player_a")
        s2 = FaceGenerationSpec.seed_from_id("player_b")
        assert s1 != s2

    def test_from_tier_a(self):
        char = _tier_a()
        spec = FaceGenerationSpec.from_character(char)
        assert spec.character_id == "test_player"
        assert spec.role == "striker"
        assert spec.seed == FaceGenerationSpec.seed_from_id("test_player")

    def test_from_tier_d(self):
        seed = TierDSeed(
            role=CharacterRole.DEFENDER, skill_rating=0.5
        )
        spec = FaceGenerationSpec.from_character(seed, "opp_1")
        assert spec.character_id == "opp_1"
        assert spec.role == "defender"

    def test_to_dict(self):
        spec = FaceGenerationSpec(
            character_id="test",
            seed=12345,
            role="striker",
        )
        d = spec.to_dict()
        assert d["character_id"] == "test"
        assert d["seed"] == 12345


class TestPlaceholderFace:
    def test_generates_rgba_image(self):
        spec = FaceGenerationSpec(character_id="test", seed=42)
        img = generate_placeholder_face(spec)
        assert isinstance(img, Image.Image)
        assert img.mode == "RGBA"
        assert img.size == (512, 512)

    def test_deterministic(self):
        spec = FaceGenerationSpec(character_id="test", seed=42)
        img1 = generate_placeholder_face(spec)
        img2 = generate_placeholder_face(spec)
        assert img1.tobytes() == img2.tobytes()

    def test_different_seeds_different_images(self):
        img1 = generate_placeholder_face(
            FaceGenerationSpec(character_id="a", seed=1)
        )
        img2 = generate_placeholder_face(
            FaceGenerationSpec(character_id="b", seed=2)
        )
        assert img1.tobytes() != img2.tobytes()


class TestApplyOverlay:
    def test_produces_rgba(self):
        base = Image.new("RGBA", (64, 64), (200, 180, 160, 255))
        result = apply_overlay(base, Expression.CONFIDENT, 0.5)
        assert result.mode == "RGBA"
        assert result.size == (64, 64)

    def test_neutral_low_intensity_nearly_unchanged(self):
        base = Image.new("RGBA", (64, 64), (200, 180, 160, 255))
        result = apply_overlay(base, Expression.NEUTRAL, 0.0)
        # With 0 intensity the overlay alpha is 0 → image unchanged.
        assert result.tobytes() == base.tobytes()

    def test_different_expressions_differ(self):
        base = Image.new("RGBA", (64, 64), (200, 180, 160, 255))
        r1 = apply_overlay(base, Expression.AGGRESSIVE, 0.8)
        r2 = apply_overlay(base, Expression.WARM, 0.8)
        assert r1.tobytes() != r2.tobytes()


class TestTeamPalette:
    def test_round_trip(self):
        p = TeamPalette(primary=(10, 20, 30), secondary=(200, 210, 220))
        d = p.to_dict()
        restored = TeamPalette.from_dict(d)
        assert restored.primary == (10, 20, 30)
        assert restored.secondary == (200, 210, 220)


class TestCharacterVisual:
    def test_render_creates_cached_file(self, tmp_path: Path):
        spec = FaceGenerationSpec(character_id="test_cv", seed=99)
        vis = CharacterVisual(
            character_id="test_cv",
            spec=spec,
            _cache_root=tmp_path,
        )
        path = vis.render(Expression.NEUTRAL, 0.5, Pose.STANDING)
        assert Path(path).exists()
        assert path.endswith(".png")

    def test_cached_render_returns_same_path(self, tmp_path: Path):
        spec = FaceGenerationSpec(character_id="test_cv2", seed=100)
        vis = CharacterVisual(
            character_id="test_cv2",
            spec=spec,
            _cache_root=tmp_path,
        )
        p1 = vis.render(Expression.WARM, 0.6)
        p2 = vis.render(Expression.WARM, 0.6)
        assert p1 == p2

    def test_different_expressions_different_paths(self, tmp_path: Path):
        spec = FaceGenerationSpec(character_id="test_cv3", seed=101)
        vis = CharacterVisual(
            character_id="test_cv3",
            spec=spec,
            _cache_root=tmp_path,
        )
        p1 = vis.render(Expression.CONFIDENT, 0.7)
        p2 = vis.render(Expression.DOUBTFUL, 0.7)
        assert p1 != p2

    def test_ensure_base_face(self, tmp_path: Path):
        spec = FaceGenerationSpec(character_id="warmup", seed=200)
        vis = CharacterVisual(
            character_id="warmup",
            spec=spec,
            _cache_root=tmp_path,
        )
        path = vis.ensure_base_face()
        assert Path(path).exists()
        assert "warmup.png" in path


class TestVisualManager:
    def test_get_visual_lazy_creates(self, tmp_path: Path):
        mgr = VisualManager(cache_root=tmp_path)
        char = _tier_a()
        vis = mgr.get_visual(char)
        assert vis.character_id == "test_player"
        # Second call returns same instance.
        assert mgr.get_visual(char) is vis

    def test_warm_up_generates_faces(self, tmp_path: Path):
        mgr = VisualManager(cache_root=tmp_path)
        chars = {
            "p1": _tier_a(),
            "p2": TierBCharacter(
                id="p2",
                name="NPC",
                role=CharacterRole.DEFENDER,
                stats={StatName.STRENGTH: 0.7},
            ),
        }
        # Override char ids for this test.
        chars["p1"].id = "p1"  # type: ignore
        mgr.warm_up(chars)  # type: ignore
        assert "p1" in mgr.visuals
        assert "p2" in mgr.visuals
        assert Path(mgr.visuals["p1"].base_face_path).exists()
        assert Path(mgr.visuals["p2"].base_face_path).exists()

    def test_render_character_produces_file(self, tmp_path: Path):
        mgr = VisualManager(cache_root=tmp_path)
        char = _tier_a()
        path = mgr.render_character(char, mood=0.0)
        assert Path(path).exists()

    def test_render_tier_d(self, tmp_path: Path):
        mgr = VisualManager(cache_root=tmp_path)
        seed = TierDSeed(role=CharacterRole.STRIKER, skill_rating=0.6)
        path = mgr.render_character(seed, character_id="opp_1")
        assert Path(path).exists()


class TestBackgroundGeneration:
    def test_known_location(self, tmp_path: Path):
        path = get_background("locker_room", cache_root=tmp_path)
        assert path is not None
        assert Path(path).exists()

    def test_unknown_location(self, tmp_path: Path):
        path = get_background("nonexistent_place", cache_root=tmp_path)
        assert path is None

    def test_cached_second_call(self, tmp_path: Path):
        p1 = get_background("stadium", cache_root=tmp_path)
        p2 = get_background("stadium", cache_root=tmp_path)
        assert p1 == p2


class TestCompositeSprite:
    """Phase 10 — layered composite rendering."""

    def test_select_layers_filters_by_expression(self):
        layers = [
            SpriteLayer(name="body", z_order=0),
            SpriteLayer(
                name="smile", z_order=10, expression=Expression.WARM
            ),
            SpriteLayer(
                name="frown", z_order=10, expression=Expression.ANXIOUS
            ),
        ]
        kept = select_layers(layers, Expression.WARM, Pose.STANDING)
        names = [l.name for l in kept]
        assert "body" in names and "smile" in names and "frown" not in names

    def test_select_layers_falls_back_to_neutral(self):
        layers = [
            SpriteLayer(name="body", z_order=0),
            SpriteLayer(
                name="neutral", z_order=10, expression=Expression.NEUTRAL
            ),
            SpriteLayer(
                name="warm", z_order=10, expression=Expression.WARM
            ),
        ]
        # Request an expression with no specific layer; NEUTRAL should fill in.
        kept = select_layers(layers, Expression.CONFIDENT, Pose.STANDING)
        names = [l.name for l in kept]
        assert "neutral" in names and "warm" not in names

    def test_select_layers_sorts_by_z_order(self):
        layers = [
            SpriteLayer(name="c", z_order=30),
            SpriteLayer(name="a", z_order=0),
            SpriteLayer(name="b", z_order=10),
        ]
        kept = select_layers(layers, Expression.NEUTRAL, Pose.STANDING)
        assert [l.name for l in kept] == ["a", "b", "c"]

    def test_composite_render_produces_file(self, tmp_path: Path):
        spec = FaceGenerationSpec(character_id="composite_test", seed=321)
        vis = CharacterVisual(
            character_id="composite_test",
            spec=spec,
            layers=procedural_layers(spec),
            _cache_root=tmp_path,
        )
        path = vis.render(Expression.NEUTRAL, 0.5, Pose.STANDING)
        assert Path(path).exists()
        # Composite cache path should be in the composites dir.
        assert "composites" in path

    def test_composite_cache_varies_by_expression_and_pose(
        self, tmp_path: Path
    ):
        spec = FaceGenerationSpec(character_id="composite_cache", seed=322)
        layers = procedural_layers(spec)
        vis = CharacterVisual(
            character_id="composite_cache",
            spec=spec,
            layers=layers,
            _cache_root=tmp_path,
        )
        p1 = vis.render(Expression.CONFIDENT, 0.5, Pose.STANDING)
        p2 = vis.render(Expression.CONFIDENT, 0.5, Pose.DEJECTED)
        p3 = vis.render(Expression.ANXIOUS, 0.5, Pose.STANDING)
        assert len({p1, p2, p3}) == 3

    def test_sprite_layer_round_trip(self):
        original = SpriteLayer(
            name="hair",
            tint=(100, 50, 20),
            z_order=20,
            expression=Expression.WARM,
            pose=Pose.STANDING,
            tint_strength=0.75,
        )
        restored = SpriteLayer.from_dict(original.to_dict())
        assert restored.name == "hair"
        assert restored.tint == (100, 50, 20)
        assert restored.z_order == 20
        assert restored.expression is Expression.WARM
        assert restored.pose is Pose.STANDING
        assert restored.tint_strength == 0.75

    def test_procedural_layers_deterministic(self):
        spec = FaceGenerationSpec(character_id="pd_det", seed=77)
        l1 = procedural_layers(spec)
        l2 = procedural_layers(spec)
        assert [layer.tint for layer in l1] == [layer.tint for layer in l2]


class TestSessionVisualIntegration:
    """Verify GameSession creates and exposes VisualManager."""

    def test_new_game_has_visual_manager(self):
        from engine.session import GameSession

        session = GameSession.new_game("Test Player", seed=1)
        assert session.visual_manager is not None
        assert isinstance(session.visual_manager, VisualManager)

    def test_warm_up_runs_on_new_game(self, tmp_path: Path):
        from engine.session import GameSession

        session = GameSession.new_game("Test Player", seed=1)
        # Player should be in visual manager.
        assert "player" in session.visual_manager.visuals
