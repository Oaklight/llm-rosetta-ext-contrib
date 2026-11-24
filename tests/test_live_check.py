"""The live ACP check's response readers.

The network steps need a signed-in lane and a running gateway, so they stay
manual.  The decisions that turn a reply into a verdict are pure and are
pinned here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _live():
    if "check_acp_live" in sys.modules:
        return sys.modules["check_acp_live"]
    path = _ROOT / "scripts" / "check_acp_live.py"
    spec = importlib.util.spec_from_file_location("check_acp_live", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_acp_live"] = module
    spec.loader.exec_module(module)
    return module


def test_a_tool_use_block_is_found_between_text_blocks():
    payload = {
        "content": [
            {"type": "text", "text": "calling"},
            {"type": "tool_use", "id": "call_1", "name": "echo", "input": {}},
        ]
    }

    assert _live().tool_use_of(payload)["id"] == "call_1"


def test_a_text_only_turn_is_not_a_tool_call():
    with pytest.raises(_live().CheckError, match="no tool_use"):
        _live().tool_use_of({"content": [{"type": "text", "text": "ping"}]})


def test_text_blocks_are_joined_without_thinking():
    payload = {
        "content": [
            {"type": "thinking", "thinking": "plan"},
            {"type": "text", "text": "pi"},
            {"type": "text", "text": "ng"},
        ]
    }

    assert _live().text_of(payload) == "ping"


def test_a_reply_without_content_has_no_text():
    assert _live().text_of({}) == ""
