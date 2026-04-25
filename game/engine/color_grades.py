"""Colour-grade pipeline (addendum §1.3).

Three independent layers — **time-of-day**, **weather**, and **mood** —
each contribute a tinted solid-colour PNG that Ren'Py composites on top
of the live background. Grades are static lookup tables; the runtime
just picks the right PNG for the current ``SceneAtmosphere`` and lets
ATL crossfade between them on condition change.

Design contract:

- Grade tables are authored constants. They render to PNGs once at
  ``generate_grade_pngs(...)`` time, with a hash-keyed cache so we
  regenerate only when the source tables change.
- ``derive_mood(...)`` and ``draw_weather(...)`` are deterministic
  given an injected RNG / state — no module-level randomness.
- Time-of-day derives from the hour-precision world clock, not from
  the block being played, so the same block (e.g. a drama event) can
  read as morning on one day and evening on another.
"""

from __future__ import annotations

import hashlib
import json
import random as _random
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TimeOfDay(str, Enum):
    DAWN = "dawn"
    MORNING = "morning"
    MIDDAY = "midday"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class Weather(str, Enum):
    CLEAR = "clear"
    OVERCAST = "overcast"
    RAIN = "rain"


class SceneMood(str, Enum):
    NEUTRAL = "neutral"
    TENSE = "tense"
    EUPHORIC = "euphoric"
    MELANCHOLY = "melancholy"
    CHARGED = "charged"


# ---------------------------------------------------------------------------
# ColorGrade dataclass + lookup tables (addendum §1.3 verbatim)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColorGrade:
    """A tint pass: solid colour + alpha, plus brightness/saturation
    scalars for downstream pipelines that can use them.

    The rendered PNG only uses ``tint``; ``alpha`` is applied at ATL
    composite time, and ``brightness``/``saturation`` are reserved for
    the future SD pipeline (which can render scenes at a target
    brightness/saturation directly rather than tinting at composite).
    """

    tint: str  # hex without leading '#', e.g. "FF8C42"
    alpha: float
    brightness: float = 1.0
    saturation: float = 1.0


TIME_OF_DAY_GRADES: dict[TimeOfDay, ColorGrade] = {
    TimeOfDay.DAWN:      ColorGrade("FF8C42", 0.12, 0.85, 0.90),
    TimeOfDay.MORNING:   ColorGrade("FFF4E0", 0.06, 1.00, 1.00),
    TimeOfDay.MIDDAY:    ColorGrade("FFFFFF", 0.00, 1.05, 1.05),
    TimeOfDay.AFTERNOON: ColorGrade("FFD580", 0.10, 0.95, 0.95),
    TimeOfDay.EVENING:   ColorGrade("FF6B35", 0.18, 0.80, 0.85),
    TimeOfDay.NIGHT:     ColorGrade("1A1A3E", 0.30, 0.60, 0.70),
}

WEATHER_GRADES: dict[Weather, ColorGrade] = {
    Weather.CLEAR:    ColorGrade("FFFACD", 0.08, 1.10, 1.10),
    Weather.OVERCAST: ColorGrade("8899AA", 0.15, 0.85, 0.80),
    Weather.RAIN:     ColorGrade("445566", 0.20, 0.75, 0.70),
}

MOOD_GRADES: dict[SceneMood, ColorGrade] = {
    SceneMood.NEUTRAL:    ColorGrade("FFFFFF", 0.00, 1.00, 1.00),
    SceneMood.TENSE:      ColorGrade("330000", 0.08, 1.00, 0.90),
    SceneMood.EUPHORIC:   ColorGrade("FFFFAA", 0.10, 1.05, 1.15),
    SceneMood.MELANCHOLY: ColorGrade("334466", 0.12, 0.90, 0.75),
    SceneMood.CHARGED:    ColorGrade("FF4400", 0.06, 1.00, 1.10),
}


# ---------------------------------------------------------------------------
# Atmosphere carrier
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SceneAtmosphere:
    """The current scene's environmental context.

    Drives grade selection, overlay selection (Phase 11C), and could
    feed narrative prompts later. Immutable so callers can pass it
    around without worrying about aliasing.
    """

    time_of_day: TimeOfDay
    weather: Weather
    mood: SceneMood
    weather_tendency: Weather  # the week's "mode" — useful for narration too


# ---------------------------------------------------------------------------
# Time-of-day mapping (clock-driven)
# ---------------------------------------------------------------------------


# Hour-of-day → TimeOfDay grade band. Authored to feel right with the
# slot anchors at 08/12/16/20 and the lookup tints in TIME_OF_DAY_GRADES.
# Boundaries are inclusive of the start hour and exclusive of the next.
_HOUR_BANDS: tuple[tuple[int, TimeOfDay], ...] = (
    (5,  TimeOfDay.DAWN),       # 05:00–06:59
    (7,  TimeOfDay.MORNING),    # 07:00–10:59
    (11, TimeOfDay.MIDDAY),     # 11:00–14:59
    (15, TimeOfDay.AFTERNOON),  # 15:00–18:59
    (19, TimeOfDay.EVENING),    # 19:00–21:59
    (22, TimeOfDay.NIGHT),      # 22:00–04:59
)


def time_of_day_for_hour(hour: int) -> TimeOfDay:
    """Project an hour-of-day onto a ``TimeOfDay`` grade.

    The bands span the slot anchors with a little margin on either side
    so the grade transition reads as gradual rather than abrupt at slot
    boundaries (a 12:00 midday slot still feels like late morning at
    11:55 and full midday by 12:30).
    """
    hour %= 24
    chosen = TimeOfDay.NIGHT
    for start, tod in _HOUR_BANDS:
        if hour >= start:
            chosen = tod
        else:
            break
    return chosen


# ---------------------------------------------------------------------------
# Weather draw — per-week tendency, per-slot biased variation
# ---------------------------------------------------------------------------


# Weather neighbours for the per-slot drift draw. RAIN doesn't drift
# directly to CLEAR (or vice versa) — that would feel too jumpy.
WEATHER_NEIGHBORS: dict[Weather, list[Weather]] = {
    Weather.CLEAR:    [Weather.OVERCAST],
    Weather.OVERCAST: [Weather.CLEAR, Weather.RAIN],
    Weather.RAIN:     [Weather.OVERCAST],
}


# Probability the per-slot draw lands on the week's tendency. The
# remainder is split among neighbours in WEATHER_NEIGHBORS.
TENDENCY_PROBABILITY = 0.7


def draw_weather_tendency(rng: _random.Random) -> Weather:
    """Roll the week's weather mode. Uniform over Weather values."""
    return rng.choice(list(Weather))


def draw_weather(tendency: Weather, rng: _random.Random) -> Weather:
    """Per-slot weather, biased toward `tendency`."""
    if rng.random() < TENDENCY_PROBABILITY:
        return tendency
    neighbors = WEATHER_NEIGHBORS.get(tendency, [tendency])
    if not neighbors:
        return tendency
    return rng.choice(neighbors)


# ---------------------------------------------------------------------------
# Mood derivation
# ---------------------------------------------------------------------------


def derive_mood(team_morale: float, momentum: float) -> SceneMood:
    """Project current sim state onto a mood enum.

    Thresholds tuned for [-1, 1] range on both inputs:
    - Strong positive morale + positive momentum → EUPHORIC
    - Strong negative morale → MELANCHOLY
    - Big momentum swings either way → CHARGED
    - Mild negative pressure → TENSE
    - Otherwise NEUTRAL.

    Order matters: the most specific bands check first.
    """
    if team_morale > 0.4 and momentum > 0.3:
        return SceneMood.EUPHORIC
    if team_morale < -0.4:
        return SceneMood.MELANCHOLY
    if abs(momentum) > 0.6:
        return SceneMood.CHARGED
    if team_morale < -0.1:
        return SceneMood.TENSE
    return SceneMood.NEUTRAL


# ---------------------------------------------------------------------------
# PNG generation + cache
# ---------------------------------------------------------------------------


_INDEX_NAME = "_index.json"


def _grade_filename(category: str, key: str) -> str:
    return f"{category}_{key}.png"


def _all_grades() -> list[tuple[str, str, ColorGrade]]:
    """Flatten the three lookup tables into ``(category, key, grade)``."""
    out: list[tuple[str, str, ColorGrade]] = []
    for tod, grade in TIME_OF_DAY_GRADES.items():
        out.append(("time", tod.value, grade))
    for w, grade in WEATHER_GRADES.items():
        out.append(("weather", w.value, grade))
    for m, grade in MOOD_GRADES.items():
        out.append(("mood", m.value, grade))
    return out


def _table_hash() -> str:
    """Stable hash of the three grade tables. Changes when authors
    edit colours, alphas, or scalars; otherwise constant across runs."""
    payload = []
    for category, key, grade in _all_grades():
        payload.append((category, key, grade.tint, grade.alpha,
                        grade.brightness, grade.saturation))
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    s = hex_str.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"expected 6-char hex, got {hex_str!r}")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def generate_grade_pngs(
    grades_dir: Path,
    *,
    pixel_size: int = 16,
) -> dict[tuple[str, str], Path]:
    """Render every grade as a small solid-colour PNG into `grades_dir`.

    Returns a `{(category, key): absolute_path}` map. Skips work when
    the on-disk index hash matches the current tables — designers
    don't need to delete the directory after edits, the hash takes
    care of invalidation.
    """
    from PIL import Image

    grades_dir = Path(grades_dir)
    grades_dir.mkdir(parents=True, exist_ok=True)
    index_path = grades_dir / _INDEX_NAME
    current_hash = _table_hash()

    # Skip regen when the cached hash matches and every expected file
    # is still on disk (catches the "user deleted one PNG" case too).
    cached: dict | None = None
    if index_path.exists():
        try:
            cached = json.loads(index_path.read_text())
        except (json.JSONDecodeError, OSError):
            cached = None

    paths: dict[tuple[str, str], Path] = {
        (cat, key): grades_dir / _grade_filename(cat, key)
        for cat, key, _ in _all_grades()
    }
    all_present = all(p.exists() for p in paths.values())

    if (
        cached is not None
        and cached.get("hash") == current_hash
        and all_present
    ):
        return paths

    for (cat, key), out_path in paths.items():
        grade = _grade_for(cat, key)
        rgb = _hex_to_rgb(grade.tint)
        Image.new("RGB", (pixel_size, pixel_size), rgb).save(str(out_path), "PNG")

    index_path.write_text(json.dumps(
        {"hash": current_hash, "files": [str(p.name) for p in paths.values()]},
        indent=2,
    ))
    return paths


def _grade_for(category: str, key: str) -> ColorGrade:
    if category == "time":
        return TIME_OF_DAY_GRADES[TimeOfDay(key)]
    if category == "weather":
        return WEATHER_GRADES[Weather(key)]
    if category == "mood":
        return MOOD_GRADES[SceneMood(key)]
    raise KeyError(f"unknown grade category: {category!r}")


def grade_path(grades_dir: Path, category: str, key: str) -> Path:
    """Resolve the PNG path for a single grade by `(category, key)`."""
    return Path(grades_dir) / _grade_filename(category, key)
