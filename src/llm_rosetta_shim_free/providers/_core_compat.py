"""Transition bridge for llm-rosetta cores before 0.14.0.dev35.

Core 0.14.0.dev35 moved the shim-facing names into ``llm_rosetta.contracts``.
A gateway preset tracks this repository's ``main`` with no pinned ref, so a
merged commit reaches gateways still running an older core; each name below is
taken from ``llm_rosetta.contracts`` when the core has it and from its earlier
home otherwise.  Remove this module once ``llm-rosetta>=0.14.0`` is the floor,
and no later than 0.15.0.

It lives under ``providers/`` because the release archive is rooted there: a
module outside that directory would not ship to a gateway that loads the
archive, and ``transforms.py`` reaches this one by relative import inside the
loader's namespace for the providers root.

It must not import ``llm_rosetta.api``: the entry point runs during
``import llm_rosetta``, when that module cannot be imported yet.
"""

from __future__ import annotations

try:
    from llm_rosetta.contracts.shim import (
        load_providers_from_dir,
    )
except ImportError:  # a core before 0.14.0.dev35
    from llm_rosetta.shims import (  # type: ignore[no-redef]
        load_providers_from_dir,
    )

try:
    from llm_rosetta.contracts.transform import (
        NamedTransform,
        hoist_late_system_messages,
    )
except ImportError:  # a core before 0.14.0.dev35
    from llm_rosetta.transforms import (  # type: ignore[no-redef]
        _NamedTransform as NamedTransform,
        hoist_late_system_messages,
    )

__all__ = [
    "NamedTransform",
    "hoist_late_system_messages",
    "load_providers_from_dir",
]
