"""The core-compat bridge resolves every name it promises, from the right home."""

from __future__ import annotations

import ast
import importlib
import inspect

import pytest

from llm_rosetta_shim_free.providers import _core_compat

#: The names this package takes from the core, by ``llm_rosetta.contracts`` module.
CONTRACT_NAMES = {
    "shim": ("load_providers_from_dir",),
    "transform": (
        "NamedTransform",
        "hoist_late_system_messages",
    ),
}

#: Where a core before 0.14.0.dev35 keeps each contract module's names.
OLD_HOMES = {
    "shim": "llm_rosetta.shims",
    "auth": "llm_rosetta.shims.auth_exchange",
    "quota": "llm_rosetta.shims.quota_probe",
    "transform": "llm_rosetta.transforms",
}

#: Old spellings that differ from the contract name.
OLD_SPELLINGS = {"NamedTransform": "_NamedTransform"}


def _core_has_contracts() -> bool:
    try:
        importlib.import_module("llm_rosetta.contracts")
    except ImportError:
        return False
    return True


def test_the_bridge_exports_exactly_the_names_the_package_uses():
    expected = sorted(n for names in CONTRACT_NAMES.values() for n in names)
    assert sorted(_core_compat.__all__) == expected


@pytest.mark.parametrize("contract", sorted(CONTRACT_NAMES))
def test_every_name_comes_from_the_home_this_core_offers(contract):
    if _core_has_contracts():
        home, spell = importlib.import_module(f"llm_rosetta.contracts.{contract}"), {}
    else:
        home, spell = importlib.import_module(OLD_HOMES[contract]), OLD_SPELLINGS
    for name in CONTRACT_NAMES[contract]:
        assert getattr(_core_compat, name) is getattr(home, spell.get(name, name)), name


def test_the_bridge_does_not_import_llm_rosetta_api():
    """The entry point runs during ``import llm_rosetta``, before ``api`` can load."""
    tree = ast.parse(inspect.getsource(_core_compat))
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(m and m.startswith("llm_rosetta.api") for m in imported)
