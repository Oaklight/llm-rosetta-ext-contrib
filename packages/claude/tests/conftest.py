"""Bind this folder as ``llm_rosetta_ext.claude`` for in-place test runs.

An installed extension is imported as ``llm_rosetta_ext.<id>``.  CI runs this
folder without installing its wheel, so bind the package here; its
``transport`` submodule then resolves from the same folder.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_PACKAGES = Path(__file__).resolve().parents[2]
_FOLDER = _PACKAGES / "claude"


def _bind_package() -> None:
    if "llm_rosetta_ext.claude" in sys.modules:
        return
    namespace = sys.modules.setdefault(
        "llm_rosetta_ext", types.ModuleType("llm_rosetta_ext")
    )
    if not hasattr(namespace, "__path__"):
        namespace.__path__ = []  # type: ignore[attr-defined]
    spec = importlib.util.spec_from_file_location(
        "llm_rosetta_ext.claude",
        _FOLDER / "__init__.py",
        submodule_search_locations=[str(_FOLDER)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["llm_rosetta_ext.claude"] = module
    spec.loader.exec_module(module)


_bind_package()
