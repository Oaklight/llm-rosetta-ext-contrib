"""What the Claude extension registers with the gateway."""

from __future__ import annotations

from llm_rosetta_ext.claude.transport import TRANSPORTS, ClaudeCliTransport


def test_the_manifest_transport_maps_to_its_factory():
    """``provides.transports`` names ``claude_cli``; the gateway reads it here."""
    assert TRANSPORTS == {"claude_cli": ClaudeCliTransport}


def test_the_factory_accepts_the_gateway_timeout():
    """The gateway builds a lane with ``factory(timeout=...)``."""
    transport = TRANSPORTS["claude_cli"](timeout=1)

    assert isinstance(transport, ClaudeCliTransport)
