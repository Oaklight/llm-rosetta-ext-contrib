"""MiniMax chat transforms.

Ported from llm-rosetta tests/test_transforms.py (TestBuiltinTransforms) and
tests/test_provider_reasoning_transforms.py (#1660 S7).
"""

from __future__ import annotations

import pytest

from llm_rosetta.api import get_shim
from llm_rosetta.contracts.transform import apply_transforms

from llm_rosetta_shim_contrib.providers.minimax.llm.chat_completions.transforms import (
    _inject_reasoning_split,
    _parse_think_tags,
)


@pytest.fixture()
def _registered(register):
    register("minimax")


def test_minimax_strips_unsupported(_registered):
    shim = get_shim("minimax--chat_completions")
    assert shim is not None
    body = {
        "model": "MiniMax-M2",
        "logprobs": True,
        "top_logprobs": 3,
        "seed": 42,
        "stop": ["END"],
        "temperature": 0.8,
        "messages": [],
    }
    result = apply_transforms(shim.post_ir_transforms, body)
    assert "logprobs" not in result
    assert "top_logprobs" not in result
    assert "seed" not in result
    assert "stop" not in result
    assert result["model"] == "MiniMax-M2"
    assert result["temperature"] == 0.8


class TestInjectReasoningSplit:
    def test_injects_when_thinking_present(self):
        body = {"thinking": {"type": "adaptive"}, "messages": []}
        result = _inject_reasoning_split(body)
        assert result["reasoning_split"] is True

    def test_no_inject_without_thinking(self):
        body = {"messages": []}
        result = _inject_reasoning_split(body)
        assert "reasoning_split" not in result

    def test_no_overwrite_existing_reasoning_split(self):
        body = {"thinking": {"type": "adaptive"}, "reasoning_split": False}
        result = _inject_reasoning_split(body)
        assert result["reasoning_split"] is False


def _msg_body(content, **extra):
    return {
        "choices": [{"message": {"role": "assistant", "content": content, **extra}}]
    }


class TestParseThinkTags:
    def test_single_think_tag(self):
        result = _parse_think_tags(
            _msg_body("<think>Let me reason.</think>The answer is 42.")
        )
        msg = result["choices"][0]["message"]
        assert msg["reasoning_content"] == "Let me reason."
        assert msg["content"] == "The answer is 42."

    def test_multiple_think_tags(self):
        result = _parse_think_tags(
            _msg_body("<think>Step 1.</think>Middle text.<think>Step 2.</think>Final.")
        )
        msg = result["choices"][0]["message"]
        assert msg["reasoning_content"] == "Step 1.\nStep 2."
        assert msg["content"] == "Middle text.Final."

    def test_no_think_tags(self):
        result = _parse_think_tags(_msg_body("Just a normal response."))
        msg = result["choices"][0]["message"]
        assert "reasoning_content" not in msg
        assert msg["content"] == "Just a normal response."

    def test_skip_when_reasoning_content_exists(self):
        result = _parse_think_tags(
            _msg_body(
                "<think>Should not parse.</think>Answer.",
                reasoning_content="Already split.",
            )
        )
        msg = result["choices"][0]["message"]
        assert msg["reasoning_content"] == "Already split."
        assert "<think>" in msg["content"]

    def test_no_choices(self):
        body = {"error": "something"}
        assert _parse_think_tags(body) == body
