"""Load authored blueprints from `content/events/`.

Content files are plain Python modules that export a `BLUEPRINTS` list of
`EventBlueprint` instances. Python (not YAML) because filters and weight
rules are closures — authoring them as data is more trouble than worth.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from types import ModuleType

from .background_pool import SceneGraphSpec
from .events import EventBlueprint
from .narrative import NarrativeTemplate


def _collect(
    package: ModuleType,
    attr: str,
    expected_type: type,
) -> list:
    """Walk the package's modules and gather `attr` entries of the expected type."""
    items = []
    seen_ids: set[str] = set()
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        entries = getattr(module, attr, [])
        for entry in entries:
            if not isinstance(entry, expected_type):
                raise TypeError(
                    f"{package.__name__}.{info.name}: non-{expected_type.__name__} in {attr}"
                )
            if entry.id in seen_ids:
                raise ValueError(
                    f"duplicate {expected_type.__name__} id: {entry.id!r}"
                )
            seen_ids.add(entry.id)
            items.append(entry)
    return items


def load_blueprints_from_package(package: ModuleType) -> list[EventBlueprint]:
    """Import every submodule of `package` and collect `BLUEPRINTS` lists."""
    return _collect(package, "BLUEPRINTS", EventBlueprint)


def load_templates_from_package(package: ModuleType) -> list[NarrativeTemplate]:
    return _collect(package, "TEMPLATES", NarrativeTemplate)


def _import_package(content_root: Path) -> ModuleType:
    """Ensure `content_root`'s parent is on sys.path, then import it by name."""
    import sys

    content_root = content_root.resolve()
    parent = str(content_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    return importlib.import_module(content_root.name)


def load_blueprints_from_path(content_root: Path) -> list[EventBlueprint]:
    """Load blueprints from a filesystem path (for tests / notebooks)."""
    return load_blueprints_from_package(_import_package(content_root))


def load_templates_from_path(content_root: Path) -> list[NarrativeTemplate]:
    return load_templates_from_package(_import_package(content_root))


def load_scene_specs_from_package(package: ModuleType) -> list[SceneGraphSpec]:
    """Import every submodule of `package` and collect `SPECS` lists.

    Scene specs use `spec_id` rather than `id`, so the duplicate check
    runs on that attribute instead of going through `_collect`.
    """
    import importlib
    import pkgutil

    items: list[SceneGraphSpec] = []
    seen_ids: set[str] = set()
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        entries = getattr(module, "SPECS", [])
        for entry in entries:
            if not isinstance(entry, SceneGraphSpec):
                raise TypeError(
                    f"{package.__name__}.{info.name}: non-SceneGraphSpec in SPECS"
                )
            if entry.spec_id in seen_ids:
                raise ValueError(
                    f"duplicate SceneGraphSpec spec_id: {entry.spec_id!r}"
                )
            seen_ids.add(entry.spec_id)
            items.append(entry)
    return items


def load_scene_specs_from_path(content_root: Path) -> list[SceneGraphSpec]:
    return load_scene_specs_from_package(_import_package(content_root))
