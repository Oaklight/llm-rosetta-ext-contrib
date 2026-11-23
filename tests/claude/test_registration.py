"""What the Claude ACP shim declares.

The lane runs ``@agentclientprotocol/claude-agent-acp``, which drives Claude
Code through the Claude Agent SDK.  The Claude sign-in lives in the CLI's own
store, so the shim is keyless.
"""

from __future__ import annotations

import pytest

from llm_rosetta.api import get_shim
from llm_rosetta_shim_contrib.providers.claude.auth import CLAUDE_ENV_UNSET

SHIM = "claude--acp"


@pytest.fixture(autouse=True)
def _registered(register):
    register("claude")


def shim():
    loaded = get_shim(SHIM)
    assert loaded is not None
    return loaded


def _requires_connection_key(name: str) -> None:
    """Skip when this core predates a connection field the shim declares.

    CI installs the core from master, so a shim branch can land before the
    core that reads a new field.  The loader ignores a key it does not know,
    which keeps the rest of the shim loadable in that window; only the
    field's own assertion has to wait for the core.
    """
    if not hasattr(shim().connection, name):
        pytest.skip(f"this core predates connection.{name}")


class TestWhatTheShimDeclares:
    def test_it_is_a_prompt_lane_on_the_acp_format(self):
        profile = shim()

        assert profile.format == "acp"
        assert profile.model_type == "llm"

    def test_the_transport_and_the_agent_command_are_declared(self):
        connection = shim().connection

        assert connection.transport == "acp"
        assert connection.acp_argv == (
            "npx",
            "-y",
            "@agentclientprotocol/claude-agent-acp@0.109.1",
        )
        assert connection.acp_env == {
            "ENABLE_TOOL_SEARCH": "false",
            "CLAUDE_CONFIG_DIR": "{acp_home}/claude",
            "npm_config_cache": "{acp_home}/npm",
        }

    def test_built_in_tools_are_switched_off_on_the_session(self):
        """The adapter keeps Claude Code's tools unless the request says no.

        The gateway's tool bridge is the only path a request's tools should
        take, so the shim declares the adapter's own switch rather than
        relying on a permission refusal after the agent already offered them.
        """
        _requires_connection_key("acp_session_meta")
        assert shim().connection.acp_session_meta == {"disableBuiltInTools": True}

    def test_billing_variables_are_kept_out_of_the_lane(self):
        """A gateway ANTHROPIC_API_KEY must not outrank the stored login."""
        _requires_connection_key("acp_env_unset")
        connection = shim().connection

        assert connection.acp_env_unset == CLAUDE_ENV_UNSET
        assert set(CLAUDE_ENV_UNSET) == {
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_MODEL",
        }

    def test_the_profile_is_the_lane_own_home(self):
        """The shim asks the gateway for this lane's home, not ``~/.claude``."""
        connection = shim().connection

        assert connection.acp_env["CLAUDE_CONFIG_DIR"] == "{acp_home}/claude"

    def test_the_adapter_install_is_cached_in_the_lane_home(self):
        """The npm cache rides the volume, so a new image reuses the install."""
        connection = shim().connection

        assert connection.acp_env["npm_config_cache"] == "{acp_home}/npm"

    def test_request_tools_are_on_by_default(self):
        """A live round trip is recorded, so a model gets the tool bridge."""
        assert shim().default_capabilities == (
            "text",
            "vision",
            "reasoning",
            "tools",
        )

    def test_it_declares_no_credential_of_its_own(self):
        """The adapter reads the host's Claude CLI login; the gateway holds none."""
        connection = shim().connection

        assert connection.keyless is True
        assert not connection.api_key_env

    def test_the_vendor_title_names_the_product(self):
        assert shim().group_label == "Anthropic (Claude)"
