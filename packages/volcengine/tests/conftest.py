"""Fixture: a clean shim registry holding this extension's folder, loaded in place."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from llm_rosetta.api import restore_registry, snapshot_registry, staging_registry
from llm_rosetta.contracts.shim import load_providers_from_dir

#: The ``packages`` directory: the parent of this extension's folder.
PACKAGES = Path(__file__).resolve().parents[2]


@pytest.fixture()
def register() -> Iterator[Callable[..., None]]:
    """Return ``register(*vendors)``: load those folders into a clean registry.

    The registry the test found is restored afterwards.
    """
    saved = snapshot_registry()

    def _register(*vendors: str) -> None:
        with staging_registry():  # starts empty: only these folders are present
            load_providers_from_dir(PACKAGES, only_paths=tuple(vendors))

    yield _register
    restore_registry(saved)
