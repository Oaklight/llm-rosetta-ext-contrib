"""The ``claude_cli`` transport."""

from __future__ import annotations

from .transport import ClaudeCliTransport

#: The transport ids this extension provides, as the gateway reads them.
TRANSPORTS = {"claude_cli": ClaudeCliTransport}

__all__ = ["TRANSPORTS", "ClaudeCliTransport"]
