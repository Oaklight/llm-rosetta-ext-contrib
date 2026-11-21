"""MiniMax shims: registration facts and reasoning declarations.

Ported from llm-rosetta tests/test_shim_loader.py, tests/test_shims.py and
tests/test_intrinsic_tool_declaration.py (#1660 S7).
"""

from __future__ import annotations

import pytest

from llm_rosetta.api import get_shim

_SHIMS = {
    "minimax--chat_completions": ("llm", "chat_completions"),
    "minimax--messages": ("llm", "messages"),
    "minimax--embedding": ("embeddings", "minimax"),
}


@pytest.fixture()
def _registered(register):
    register("minimax")


def test_third_party_providers_registered(_registered):
    for name in ("minimax--chat_completions", "minimax--messages"):
        shim = get_shim(name)
        assert shim is not None, f"Built-in shim '{name}' not registered"
        assert shim.name == name


def test_base_types_correct(_registered):
    for name, (model_type, base) in _SHIMS.items():
        shim = get_shim(name)
        assert shim is not None, f"Shim {name!r} not found"
        assert shim.model_type == model_type, name
        assert shim.format == base, (
            f"{name}: expected base={base!r}, got {shim.format!r}"
        )


def test_the_vendor_declares_no_group(_registered):
    for name in _SHIMS:
        shim = get_shim(name)
        assert shim.group is None and shim.group_label is None, name


def test_minimax_has_transforms(_registered):
    """MiniMax shim should strip fields + inject reasoning_split."""
    s = get_shim("minimax--chat_completions")
    assert s is not None
    assert len(s.post_ir_transforms) == 2  # strip_fields + inject_reasoning_split
    assert len(s.pre_ir_transforms) == 1  # parse_think_tags
    body = {
        "logprobs": True,
        "top_logprobs": 5,
        "seed": 42,
        "stop": ["\n"],
        "messages": [],
    }
    result = s.post_ir_transforms[0](body)
    assert "logprobs" not in result
    assert "top_logprobs" not in result
    assert "seed" not in result
    assert "stop" not in result
    assert "messages" in result


def test_unsigned_thinking_blocks_stay_on_the_wire(_registered):
    """MiniMax's Messages lane accepts an unsigned thinking block (#954).

    Probed live 2026-10-13: anthropic, openrouter and the opencode Messages
    lane answer 400, so they withhold it; MiniMax keeps the default.
    """
    minimax = get_shim("minimax--messages")
    assert minimax is not None
    assert minimax.reasoning is not None
    assert minimax.reasoning.unsigned_blocks == "as_is"


def test_messages_shim_keeps_the_base_reasoning_cap_fields(_registered):
    """MiniMax's Messages lane has no effort control at all (#757, #961).

    Its compatibility layer documents no effort parameter and ``none`` is what
    keeps the field off the wire.  Its own thinking modes are deliberate.
    """
    minimax = get_shim("minimax--messages")
    assert minimax is not None
    cap = minimax.reasoning
    assert cap is not None
    assert cap.thinking_modes == {
        "auto": "adaptive",
        "enabled": "adaptive",
        "disabled": "disabled",
    }
    assert cap.effort_field == "none"
    assert cap.effort_range is None
    assert cap.unsigned_blocks == "as_is"


def test_effort_ranges_match_the_documented_ladders(_registered):
    """MiniMax's Chat lane answers 400 for an unlisted value (#961)."""
    shim = get_shim("minimax--chat_completions")
    assert shim is not None
    assert shim.reasoning is not None
    assert shim.reasoning.effort_field == "reasoning_effort"
    assert shim.reasoning.effort_range == ("low", "max")


def test_messages_lane_declares_web_search_only(_registered):
    """MiniMax's Anthropic lane runs web search; code execution is not declared.

    Measured live 2026-10-23: a ``web_search_20250305`` declaration comes back
    with ``server_tool_use`` + ``web_search_tool_result`` blocks, while
    ``code_execution_20250522`` is rejected for having no schema.
    """
    shim = get_shim("minimax--messages")
    assert shim is not None
    assert set(shim.tools.intrinsic_tools) == {"web_search"}
