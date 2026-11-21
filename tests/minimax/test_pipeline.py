"""Requests run through the MiniMax shims.

Ported from llm-rosetta tests/test_pipeline.py (TestUnsignedBlocksPolicy,
TestShimEffortLadders), tests/test_intrinsic_tool_declaration.py and
tests/test_nameless_tool_definitions.py (#1660 S7).
"""

from __future__ import annotations

import pytest

from llm_rosetta.api import ConversionPipeline


@pytest.fixture(autouse=True)
def _registered(register):
    register("minimax")


def _chat_history():
    """A Chat history whose assistant turn carries reasoning, no signature."""
    return {
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "reasoning_content": "think hard",
                "content": "Hello",
            },
            {"role": "user", "content": "bye"},
        ],
    }


def _effort_body(effort):
    return {
        "model": "m",
        "reasoning_effort": effort,
        "messages": [{"role": "user", "content": "hi"}],
    }


def test_minimax_shim_keeps_unsigned_reasoning_on_the_wire():
    out = ConversionPipeline(
        "chat_completions", "messages", target_shim="minimax--messages"
    ).convert_request(_chat_history())
    blocks = [
        block
        for message in out["messages"]
        if message.get("role") == "assistant"
        for block in message.get("content", [])
        if block.get("type") == "thinking"
    ]
    assert len(blocks) == 1


def test_minimax_messages_sends_no_effort_at_all():
    """Thinking is supported there; effort is not, not even as a stray field."""
    out = ConversionPipeline(
        "chat_completions", "messages", target_shim="minimax--messages"
    ).convert_request(_effort_body("max"))
    assert "reasoning_effort" not in out
    assert "output_config" not in out
    assert out["thinking"] == {"type": "adaptive"}


@pytest.mark.parametrize(("effort", "sent"), [("minimal", "low"), ("max", "max")])
def test_minimax_chat_clamps_to_the_documented_ladder(effort, sent):
    out = ConversionPipeline(
        "chat_completions", "chat_completions", target_shim="minimax--chat_completions"
    ).convert_request(_effort_body(effort))
    assert out["reasoning_effort"] == sent


def test_minimax_lane_keeps_and_emits_web_search():
    """The declaration is load-bearing on the wire, not only in the yaml."""
    pipe = ConversionPipeline(
        "open_responses", "messages", target_shim="minimax--messages"
    )
    body = pipe.convert_request(
        {
            "model": "m",
            "max_tokens": 10,
            "input": "hi",
            "tools": [{"type": "web_search"}],
        }
    )
    assert {"type": "web_search_20250305", "name": "web_search"} in body["tools"]
    assert pipe.warnings == []


_NAMELESS: dict = {
    "model": "m",
    "max_tokens": 10,
    "messages": [{"role": "user", "content": "hi"}],
    "tools": [{"type": "intrinsic", "intrinsic_kind": "web_search"}],
}


def _messages_pipe():
    return ConversionPipeline("messages", "messages", target_shim="minimax--messages")


def test_a_nameless_tool_does_not_reach_the_wire():
    pipe = _messages_pipe()
    body = pipe.convert_request(dict(_NAMELESS))
    assert not body.get("tools")
    assert any("with no name" in warning for warning in pipe.warnings)


def test_a_named_tool_beside_a_nameless_one_still_goes_through():
    request = dict(_NAMELESS)
    request["tools"] = [
        {"type": "intrinsic", "intrinsic_kind": "web_search"},
        {"name": "lookup", "description": "", "input_schema": {"type": "object"}},
    ]
    pipe = _messages_pipe()
    body = pipe.convert_request(request)
    assert [tool.get("name") for tool in body["tools"]] == ["lookup"]
    assert any("1 tool definition(s) with no name" in w for w in pipe.warnings)


_FORCED: dict = {
    **_NAMELESS,
    "tools": [
        {"type": "intrinsic", "intrinsic_kind": "web_search"},
        {"name": "lookup", "description": "", "input_schema": {"type": "object"}},
    ],
    "tool_choice": {"type": "tool", "name": ""},
}


def test_a_choice_forcing_the_nameless_tool_does_not_survive():
    pipe = _messages_pipe()
    body = pipe.convert_request(dict(_FORCED))
    assert [tool.get("name") for tool in body["tools"]] == ["lookup"]
    assert "tool_choice" not in body
    assert any("forcing it was removed" in warning for warning in pipe.warnings)


def test_a_choice_forcing_a_surviving_tool_is_kept():
    request = dict(_FORCED)
    request["tools"] = [
        {"name": "lookup", "description": "", "input_schema": {"type": "object"}},
    ]
    request["tool_choice"] = {"type": "tool", "name": "lookup"}
    pipe = _messages_pipe()
    body = pipe.convert_request(request)
    assert body["tool_choice"] == {"type": "tool", "name": "lookup"}
    assert not any("forcing it was removed" in warning for warning in pipe.warnings)


def test_the_lone_nameless_tool_takes_its_choice_with_it():
    request = dict(_FORCED)
    request["tools"] = [{"type": "intrinsic", "intrinsic_kind": "web_search"}]
    request["tool_choice"] = {"mode": "auto"}
    pipe = _messages_pipe()
    body = pipe.convert_request(request)
    assert "tools" not in body
    assert "tool_choice" not in body
