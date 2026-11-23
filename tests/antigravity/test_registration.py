"""What the Antigravity shim declares.

Ported from llm-rosetta tests/gateway/test_antigravity_shim.py
``TestWhatTheShimDeclares`` (#1660 S7).  Shim facts are read from the contrib
copy, registered alone.
"""

from __future__ import annotations

import pytest

from llm_rosetta.api import get_shim

SHIM = "antigravity--acp"


@pytest.fixture(autouse=True)
def _registered(register):
    register("antigravity")


def shim():
    loaded = get_shim(SHIM)
    assert loaded is not None
    return loaded


class TestWhatTheShimDeclares:
    def test_it_is_a_prompt_lane_on_the_acp_format(self):
        profile = shim()

        assert profile.format == "acp"
        assert profile.model_type == "llm"

    def test_the_transport_and_the_agent_command_are_declared(self):
        connection = shim().connection

        assert connection.transport == "acp"
        assert connection.acp_argv == (
            "agy",
            "acp",
            "--dangerously-skip-permissions=false",
        )

    def test_it_declares_no_credential_of_its_own(self):
        """``agy`` owns the Google token; the gateway must not hold one."""
        connection = shim().connection

        assert connection.keyless is True
        assert not connection.api_key_env

    def test_the_lane_does_not_pin_a_shared_profile(self):
        """The gateway names a per-lane home; the shim must not fix one."""
        assert not shim().connection.acp_env

    def test_built_in_tools_are_disabled_by_the_profile_not_the_session(self):
        """``agy`` is hardened on disk, so no request-side switch is needed."""
        assert shim().connection.acp_session_meta is None

    def test_the_vendor_title_names_the_product(self):
        """Antigravity's vendor title names the product, not the directory."""
        assert shim().group_label == "Google (Antigravity)"
