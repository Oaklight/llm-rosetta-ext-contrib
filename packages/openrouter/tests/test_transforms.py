"""OpenRouter reasoning-field transform.

Ported from llm-rosetta tests/test_provider_reasoning_transforms.py (#1660 S7).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# The sidecar sits in the extension folder; load it from there, as the loader does.
_PATH = (
    Path(__file__).resolve().parents[1] / "llm" / "chat_completions" / "transforms.py"
)
_SPEC = importlib.util.spec_from_file_location("openrouter_transforms", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
_rename_reasoning_field = _MODULE._rename_reasoning_field


class TestRenameReasoningField:
    def test_renames_reasoning_to_reasoning_content(self):
        body = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Answer.",
                        "reasoning": "Let me think...",
                    }
                }
            ]
        }
        msg = _rename_reasoning_field(body)["choices"][0]["message"]
        assert msg["reasoning_content"] == "Let me think..."
        assert "reasoning" not in msg

    def test_no_rename_when_reasoning_content_exists(self):
        body = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Answer.",
                        "reasoning": "Original.",
                        "reasoning_content": "Already there.",
                    }
                }
            ]
        }
        msg = _rename_reasoning_field(body)["choices"][0]["message"]
        assert msg["reasoning_content"] == "Already there."
        assert msg["reasoning"] == "Original."

    def test_renames_on_streaming_delta(self):
        """The streaming path routes chunks through this helper too (#969 review).

        A chunk carries the text on ``delta``, so renaming only ``message``
        dropped OpenRouter's streamed reasoning.
        """
        body = {
            "choices": [
                {"index": 0, "delta": {"reasoning": "The"}, "finish_reason": None}
            ]
        }
        delta = _rename_reasoning_field(body)["choices"][0]["delta"]
        assert delta["reasoning_content"] == "The"
        assert "reasoning" not in delta

    def test_no_reasoning_field(self):
        body = {
            "choices": [{"message": {"role": "assistant", "content": "No reasoning."}}]
        }
        msg = _rename_reasoning_field(body)["choices"][0]["message"]
        assert "reasoning_content" not in msg

    def test_no_choices(self):
        body = {"error": "something"}
        assert _rename_reasoning_field(body) == body
