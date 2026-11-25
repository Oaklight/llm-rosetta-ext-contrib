"""Anthropic Claude through the official CLI: shims, sign-in exchange, transport.

Layout (everything an extension may carry):

* ``provider.yaml`` and ``llm/<format>/provider.yaml``: the shim tree
* ``auth.py``: the credential exchange sidecar
* ``transport/``: the ``claude_cli`` lane (``ClaudeCliTransport``)

The extension imports only ``llm_rosetta.contracts`` and the standard library.
"""

from __future__ import annotations

__all__ = ["__version__"]
__version__ = "0.1.0"
