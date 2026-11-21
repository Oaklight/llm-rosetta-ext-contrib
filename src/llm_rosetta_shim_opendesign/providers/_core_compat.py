"""Transition bridge for llm-rosetta cores before 0.14.0.dev35.

Core 0.14.0.dev35 moved the shim-facing names into ``llm_rosetta.contracts``.
A gateway preset tracks this repository's ``main`` with no pinned ref, so a
merged commit reaches gateways still running an older core; each name below is
taken from ``llm_rosetta.contracts`` when the core has it and from its earlier
home otherwise.  Remove this module once ``llm-rosetta>=0.14.0`` is the floor,
and no later than 0.15.0.

It lives under ``providers/`` because the release archive is rooted there: a
module outside that directory would not ship to a gateway that loads the
archive, and a ``transforms.py`` would reach this one by relative import inside the
loader's namespace for the providers root.

``auth.py`` and ``quota.py`` carry the same ``try``/``except`` inline instead of importing
this module: the loader executes them as top-level modules, so they have
no package to import it relatively from.  Their names are listed here as
well, so the tests take them from one place and check that both agree.

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
    from llm_rosetta.contracts.auth import (
        AuthContext,
        AuthExchangeError,
        BaseAuthExchange,
        InteractiveSetupRequired,
    )
except ImportError:  # a core before 0.14.0.dev35
    from llm_rosetta.shims.auth_exchange import (  # type: ignore[no-redef]
        AuthContext,
        AuthExchangeError,
        BaseAuthExchange,
        InteractiveSetupRequired,
    )

try:
    from llm_rosetta.contracts.quota import (
        QuotaProbeError,
        QuotaWindow,
        parse_iso,
        vendor_message,
    )
except ImportError:  # a core before 0.14.0.dev35
    from llm_rosetta.shims.quota_probe import (  # type: ignore[no-redef]
        QuotaProbeError,
        QuotaWindow,
        parse_iso,
        vendor_message,
    )

__all__ = [
    "AuthContext",
    "AuthExchangeError",
    "BaseAuthExchange",
    "InteractiveSetupRequired",
    "QuotaProbeError",
    "QuotaWindow",
    "load_providers_from_dir",
    "parse_iso",
    "vendor_message",
]
