"""Process-lane transports shipped beside the vendor shims that need them.

A transport here implements :mod:`llm_rosetta.contracts.transport`; the
gateway discovers it through the ``llm_rosetta_gateway.transports`` entry
point in ``pyproject.toml``.  The package does not import the gateway.
"""

from .claude_cli import ClaudeCliTransport

__all__ = ["ClaudeCliTransport"]
