"""Tests for engine.figures — figure asset model + selection."""

from pathlib import Path

from engine.characters import CharacterRole
from engine.event_taxonomy import EventTone
from engine.figures import (
    FigureAppearance,
    FigureAsset,
    FigureCategory,
    FigureManifest,
    FigurePosture,
    appearance_from_descriptor,
    category_for_role,
    posture_for,
    select_figure,
    select_for_character,
)
from engine.sprite_pool import (
    AgeBucket,
    Build,
    CharacterDescriptor,
    GenderPresentation,
    SkinTone,
)


def _desc(**kw) -> CharacterDescriptor:
    base = dict(
        gender_presentation=GenderPresentation.FEMININE,
        age_bucket=AgeBucket.ADULT,
        skin_tone=SkinTone.DARK,
        build=Build.ATHLETIC,
        hair="long_blonde",
    )
    base.update(kw)
    return CharacterDescriptor(**base)


def _asset(cat, posture, **app) -> FigureAsset:
    return FigureAsset(
        category=cat,
        appearance=FigureAppearance(**app),
        posture=posture,
        path=f"{cat.value}_{posture.value}_{'_'.join(app.values())}.png",
    )


class TestAppearanceMapping:
    def test_coarsens_axes(self):
        ap = appearance_from_descriptor(_desc())
        assert ap.gender == "feminine"
        assert ap.skin == "dark"
        assert ap.hair_color == "light"   # blonde
        assert ap.hair_length == "long"
        assert ap.age == "adult"

    def test_veteran_and_medium_skin_and_red_buzz(self):
        ap = appearance_from_descriptor(
            _desc(age_bucket=AgeBucket.VETERAN, skin_tone=SkinTone.MEDIUM,
                  hair="buzz_black", gender_presentation=GenderPresentation.MASCULINE)
        )
        assert ap.age == "older"
        assert ap.skin == "light"     # only DARK maps to dark
        assert ap.hair_color == "dark"  # black
        assert ap.hair_length == "short"  # buzz

    def test_androgynous_maps_to_a_bucket(self):
        ap = appearance_from_descriptor(
            _desc(gender_presentation=GenderPresentation.ANDROGYNOUS)
        )
        assert ap.gender in ("masculine", "feminine")


class TestPostureAndCategory:
    def test_authority_postures(self):
        assert posture_for(FigureCategory.AUTHORITY, EventTone.HOSTILE) is FigurePosture.ANGRY
        assert posture_for(FigureCategory.AUTHORITY, EventTone.WARM) is FigurePosture.COMFORTING
        assert posture_for(FigureCategory.AUTHORITY, EventTone.NEUTRAL) is FigurePosture.NEUTRAL

    def test_interlocutor_postures(self):
        assert posture_for(FigureCategory.INTERLOCUTOR, EventTone.HOSTILE) is FigurePosture.TENSE
        assert posture_for(FigureCategory.INTERLOCUTOR, EventTone.WARM) is FigurePosture.WARM

    def test_motion_and_anonymous_fixed(self):
        assert posture_for(FigureCategory.MOTION, EventTone.WARM) is FigurePosture.ACTION
        assert posture_for(FigureCategory.ANONYMOUS, EventTone.HOSTILE) is FigurePosture.PERIPHERAL

    def test_category_for_role(self):
        assert category_for_role(CharacterRole.MANAGER) is FigureCategory.AUTHORITY
        assert category_for_role(CharacterRole.PHYSIO) is FigureCategory.MEDICAL
        assert category_for_role(CharacterRole.STRIKER) is FigureCategory.INTERLOCUTOR
        assert category_for_role(CharacterRole.STRIKER, in_match=True) is FigureCategory.MOTION


class TestSelection:
    def _manifest(self, tmp_path) -> FigureManifest:
        mf = FigureManifest(assets_root=tmp_path)
        # Two interlocutor appearances × two postures.
        for gender in ("masculine", "feminine"):
            for posture in (FigurePosture.WARM, FigurePosture.TENSE):
                mf.add(_asset(
                    FigureCategory.INTERLOCUTOR, posture,
                    gender=gender, skin="light", hair_color="dark",
                    hair_length="short", age="adult",
                ))
        return mf

    def test_exact_gender_and_posture_win(self, tmp_path: Path):
        mf = self._manifest(tmp_path)
        want = FigureAppearance(gender="feminine", skin="light",
                                hair_color="dark", hair_length="short", age="adult")
        a = select_figure(mf, FigureCategory.INTERLOCUTOR, want, FigurePosture.TENSE)
        assert a.appearance.gender == "feminine"
        assert a.posture is FigurePosture.TENSE

    def test_gender_preferred_over_appearance(self, tmp_path: Path):
        mf = self._manifest(tmp_path)
        # Ask for feminine + warm with mismatched hair/skin — gender+posture
        # must still win over the appearance axes.
        want = FigureAppearance(gender="feminine", skin="dark",
                                hair_color="red", hair_length="long", age="older")
        a = select_figure(mf, FigureCategory.INTERLOCUTOR, want, FigurePosture.WARM)
        assert a.appearance.gender == "feminine"
        assert a.posture is FigurePosture.WARM

    def test_empty_category_returns_none(self, tmp_path: Path):
        mf = self._manifest(tmp_path)
        assert select_figure(
            mf, FigureCategory.MEDICAL, FigureAppearance(), FigurePosture.NEUTRAL
        ) is None

    def test_degrades_within_category_when_posture_missing(self, tmp_path: Path):
        mf = self._manifest(tmp_path)
        # No COMFORTING interlocutor exists → still returns an interlocutor
        # (right gender), not None.
        want = FigureAppearance(gender="masculine")
        a = select_figure(mf, FigureCategory.INTERLOCUTOR, want, FigurePosture.COMFORTING)
        assert a is not None
        assert a.category is FigureCategory.INTERLOCUTOR
        assert a.appearance.gender == "masculine"

    def test_select_for_character_end_to_end(self, tmp_path: Path):
        mf = self._manifest(tmp_path)
        desc = _desc(gender_presentation=GenderPresentation.FEMININE)
        a = select_for_character(
            mf, desc, CharacterRole.STRIKER, EventTone.HOSTILE,
        )
        assert a.category is FigureCategory.INTERLOCUTOR
        assert a.appearance.gender == "feminine"
        assert a.posture is FigurePosture.TENSE  # hostile → tense


class TestManifestRoundTrip:
    def test_save_load(self, tmp_path: Path):
        mf = FigureManifest(assets_root=tmp_path)
        mf.add(_asset(
            FigureCategory.AUTHORITY, FigurePosture.ANGRY,
            gender="masculine", skin="light", hair_color="dark",
            hair_length="short", age="older",
        ))
        mf.save()
        reloaded = FigureManifest.load(tmp_path)
        assert len(reloaded.assets) == 1
        a = reloaded.assets[0]
        assert a.category is FigureCategory.AUTHORITY
        assert a.posture is FigurePosture.ANGRY
        assert a.appearance.age == "older"
