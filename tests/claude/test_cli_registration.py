"""What the Claude CLI shim declares.

The lane runs the official ``claude`` CLI as a model client.  The CLI builds
and signs the upstream request itself, so the shim is keyless and declares
only the command, its environment, and the capabilities a live run measured.
"""

from __future__ import annotations

import pytest

from llm_rosetta.api import get_shim
from llm_rosetta_shim_contrib.providers.claude.auth import CLAUDE_ENV_UNSET

SHIM = "claude--messages"


@pytest.fixture(autouse=True)
def _registered(register):
    register("claude")


def shim():
    loaded = get_shim(SHIM)
    assert loaded is not None
    return loaded


class TestWhatTheShimDeclares:
    def test_it_is_a_model_client_on_the_messages_format(self):
        profile = shim()

        assert profile.format == "messages"
        assert profile.model_type == "llm"
        assert profile.connection.transport == "claude_cli"

    def test_the_vendor_command_is_declared(self):
        assert shim().connection.cli_argv == ("claude",)

    def test_user_settings_are_loaded_for_the_login_helper(self):
        """Without this the CLI starts with no credential (measured 401)."""
        assert shim().connection.cli_args == ("--setting-sources", "user")

    def test_the_lane_identifies_itself_to_the_cli(self):
        assert shim().connection.cli_env == {"CLAUDE_CODE_ENTRYPOINT": "llm-rosetta"}

    def test_billing_and_backend_variables_are_kept_out_of_the_lane(self):
        assert shim().connection.cli_env_unset == CLAUDE_ENV_UNSET

    def test_the_upstream_defaults_to_anthropics_api(self):
        """An organization gateway is a provider-entry fact, not a vendor one."""
        assert shim().connection.cli_upstream is None

    def test_it_declares_no_credential_of_its_own(self):
        connection = shim().connection

        assert connection.keyless is True
        assert not connection.api_key_env

    def test_vision_and_reasoning_are_on_by_default(self):
        """Both were measured live on CLI 2.1.299."""
        assert shim().default_capabilities == ("text", "vision", "reasoning")

    def test_tools_stay_off_until_the_definition_reaches_upstream(self):
        """A live request with a tool degraded to text, not a tool_use block."""
        assert "tools" not in shim().default_capabilities

    def test_the_vendor_title_and_logo_are_inherited(self):
        assert shim().group_label == "Anthropic (Claude)"
        assert shim().logo.endswith("/claude.svg")
