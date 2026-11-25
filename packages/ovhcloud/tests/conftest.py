"""Fixtures: load this extension's folder in place into a clean shim registry."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from llm_rosetta.api import restore_registry, snapshot_registry, staging_registry
from llm_rosetta.contracts.shim import ProviderShim, load_providers_from_dir

#: ``packages/``: the parent of this extension's folder.
PACKAGES_DIR = Path(__file__).resolve().parents[2]


def register_vendor(vendor: str) -> list[ProviderShim]:
    """Register the shims of the folder ``packages/<vendor>``."""
    return load_providers_from_dir(PACKAGES_DIR, only_paths=(vendor,))


@pytest.fixture()
def register() -> Iterator[Callable[..., None]]:
    """Return ``register(*vendors)``: load those folders into a clean registry.

    The registry the test found is restored afterwards.
    """
    saved = snapshot_registry()

    def _register(*vendors: str) -> None:
        with staging_registry():  # starts empty: only these folders are present
            for vendor in vendors:
                register_vendor(vendor)

    yield _register
    restore_registry(saved)
