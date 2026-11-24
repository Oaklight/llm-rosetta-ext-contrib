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


def test_a_tool_use_without_an_id_is_refused():
    with pytest.raises(_live().CheckError, match="no id"):
        _live().tool_use_of({"content": [{"type": "tool_use", "name": "echo"}]})


def test_a_tool_use_without_a_name_is_refused():
    with pytest.raises(_live().CheckError, match="no name"):
        _live().tool_use_of({"content": [{"type": "tool_use", "id": "call_1"}]})


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


def test_a_listing_row_must_name_its_provider_as_the_owner():
    live = _live()
    row = {"id": "m1", "owned_by": "claude-school"}

    assert live.owner_problem(row, "claude-school") is None
    assert "not 'antigravity'" in live.owner_problem(row, "antigravity")
    assert "no owner" in live.owner_problem({"id": "m1"}, "claude-school")


def test_one_good_quota_reading_passes_and_a_bad_one_warns():
    live = _live()
    payload = {
        "status": "ok",
        "credentials": [
            {
                "credential": "aaaa1111",
                "reading": {
                    "status": "ok",
                    "windows": [{"name": "5 hours", "used_percent": 0.0}],
                },
            },
            {"credential": "bbbb2222", "reading": {"status": "error"}},
        ],
    }

    summary = live.quota_summary(payload)

    assert "aaaa1111: 5 hours 0.0%" in summary
    assert "[warn] bbbb2222: no good reading" in summary


def test_no_good_quota_reading_fails():
    live = _live()
    payload = {
        "status": "ok",
        "credentials": [{"credential": "aaaa1111", "reading": {"status": "error"}}],
    }

    with pytest.raises(live.CheckError, match="no credential has a quota reading"):
        live.quota_summary(payload)


def test_an_image_over_the_limit_is_refused(tmp_path, monkeypatch):
    live = _live()
    monkeypatch.setattr(live, "_MAX_IMAGE_BYTES", 4)
    path = tmp_path / "too-big.png"
    path.write_bytes(b"\0" * 5)

    with pytest.raises(live.CheckError, match="image limit is 4"):
        live._image_block(path)


def _tool_round_trip_replies(answer, calls):
    first = {
        "stop_reason": "tool_use",
        "content": [
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "echo",
                "input": {"text": "ping"},
            }
        ],
    }
    second = {"stop_reason": "end_turn", "content": [{"type": "text", "text": answer}]}
    replies = iter([first, second])

    def fake(*args):
        calls.append(args)
        return next(replies)

    return fake


def test_the_resumed_turn_must_read_the_tool_result_not_the_prompt(monkeypatch):
    live = _live()
    calls = []
    monkeypatch.setattr(
        live, "_messages", _tool_round_trip_replies(live._RESULT_NONCE, calls)
    )
    live._check_tool_round_trip("http://gateway", None, "session", "model", 1.0)

    sent = calls[1][3]["messages"][-1]["content"][0]["content"]
    assert sent == f"echo: {live._RESULT_NONCE}"

    monkeypatch.setattr(live, "_messages", _tool_round_trip_replies("ping", []))
    with pytest.raises(live.CheckError, match="did not use the tool result"):
        live._check_tool_round_trip("http://gateway", None, "session", "model", 1.0)
