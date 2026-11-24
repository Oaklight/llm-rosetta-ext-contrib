#!/usr/bin/env python3
"""Live-check one ACP lane through a running gateway.

The unit tests drive a fake agent.  This script proves the path a gateway
actually wires together: a request's tools reach the vendor CLI over the
loopback MCP bridge, the call comes back as ``tool_use``, the client's result
resumes the same turn, a changed tool set opens a fresh session, and the
Quota card has a reading.

It is a developer tool, not shipped.  It needs a running gateway and a lane
that is already signed in; it sends real turns to the vendor's subscription.

Usage::

    python scripts/check_acp_live.py \
        --provider claude-school --model claude-haiku-4-5

    python scripts/check_acp_live.py \
        --provider antigravity --model gemini-3.8-flash-low \
        --image face.png

The gateway's API key is read from ``--api-key`` or ``GATEWAY_API_KEY``.  The
admin read is open on a loopback gateway; pass ``--admin-key`` or
``GATEWAY_ADMIN_KEY`` with the gateway's internal admin token when it is not.
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ECHO = {
    "name": "echo",
    "description": "Echo the given text back to the caller.",
    "input_schema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
}

NOOP = {
    "name": "noop",
    "description": "Do nothing and return ok.",
    "input_schema": {"type": "object", "properties": {}},
}

#: An oversized screenshot turns a useful verdict into a gateway error.
_MAX_IMAGE_BYTES = 4 << 20

#: A value the prompt never contains, so only the tool result can supply it.
_RESULT_NONCE = "kestrel-4815"


class CheckError(RuntimeError):
    """One live step did not hold."""


def _request(
    url: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Send one JSON request and return the decoded object."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers or {})
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:800]
        raise CheckError(f"{exc.code} from {url}: {detail}") from exc
    except (TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise CheckError(f"cannot reach {url}: {reason}") from exc
    except http.client.HTTPException as exc:
        raise CheckError(f"{url} sent an incomplete reply: {exc}") from exc
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise CheckError(f"{url} did not answer JSON: {raw[:300]!r}") from exc
    if not isinstance(payload, dict):
        raise CheckError(f"{url} answered {type(payload).__name__}, not an object")
    return payload


def _api_headers(key: str | None) -> dict[str, str]:
    """The bearer header a keyed gateway expects on the model and message paths."""
    return {"Authorization": f"Bearer {key}"} if key else {}


def _message_headers(key: str | None, session: str) -> dict[str, str]:
    headers = {
        "anthropic-version": "2023-06-01",
        "x-claude-code-session-id": session,
    }
    headers.update(_api_headers(key))
    return headers


def tool_use_of(payload: dict[str, Any]) -> dict[str, Any]:
    """The first ``tool_use`` block, or raise when the turn did not call one."""
    content = payload.get("content")
    if not isinstance(content, list):
        raise CheckError("the turn has no content blocks")
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            if not isinstance(block.get("id"), str) or not block["id"]:
                raise CheckError("a tool_use block has no id")
            if not isinstance(block.get("name"), str) or not block["name"]:
                raise CheckError("a tool_use block has no name")
            return block
    raise CheckError(f"no tool_use in {json.dumps(content)[:500]}")


def text_of(payload: dict[str, Any]) -> str:
    """Join the text blocks of a reply."""
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "".join(part for part in parts if isinstance(part, str)).strip()


def owner_problem(match: dict[str, Any], provider: str) -> str | None:
    """Why a listing row does not belong to the provider, or ``None``."""
    owner = match.get("owned_by")
    if owner == provider:
        return None
    if owner is None:
        return f"{match.get('id')!r} has no owner; expected {provider!r}"
    return f"{match.get('id')!r} belongs to {owner!r}, not {provider!r}"


def _check_models(
    base: str, key: str | None, provider: str, model: str, timeout: float
) -> None:
    payload = _request(f"{base}/v1/models", headers=_api_headers(key), timeout=timeout)
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise CheckError("the model list has no data")
    match = next(
        (row for row in rows if isinstance(row, dict) and row.get("id") == model),
        None,
    )
    if match is None:
        raise CheckError(f"{model!r} is not in the model list")
    problem = owner_problem(match, provider)
    if problem is not None:
        raise CheckError(problem)


def _messages(
    base: str,
    key: str | None,
    session: str,
    body: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    return _request(
        f"{base}/v1/messages",
        body=body,
        headers=_message_headers(key, session),
        timeout=timeout,
    )


def _check_count_tokens(
    base: str, key: str | None, session: str, model: str, timeout: float
) -> int:
    payload = _request(
        f"{base}/v1/messages/count_tokens",
        body={
            "model": model,
            "messages": [{"role": "user", "content": "Count this short sentence."}],
        },
        headers=_message_headers(key, session),
        timeout=timeout,
    )
    count = payload.get("input_tokens")
    if not isinstance(count, int) or count <= 0:
        raise CheckError(f"count_tokens answered {count!r}")
    return count


def _check_tool_round_trip(
    base: str,
    key: str | None,
    session: str,
    model: str,
    timeout: float,
) -> None:
    prompt = (
        "Call the echo tool with text ping. Then repeat the tool result "
        "exactly and nothing else."
    )
    first = _messages(
        base,
        key,
        session,
        {
            "model": model,
            "max_tokens": 512,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [ECHO],
        },
        timeout,
    )
    if first.get("stop_reason") != "tool_use":
        raise CheckError(
            f"the tool request stopped at {first.get('stop_reason')!r}: "
            f"{text_of(first)[:300]!r}"
        )
    call = tool_use_of(first)
    if call.get("name") != ECHO["name"]:
        raise CheckError(f"the turn called {call.get('name')!r}, not 'echo'")
    arguments = call.get("input")
    if not isinstance(arguments, dict) or arguments.get("text") != "ping":
        raise CheckError(f"the turn called echo with {arguments!r}, not text 'ping'")

    second = _messages(
        base,
        key,
        session,
        {
            "model": model,
            "max_tokens": 512,
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": first["content"]},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": call["id"],
                            "content": f"echo: {_RESULT_NONCE}",
                        }
                    ],
                },
            ],
            "tools": [ECHO],
        },
        timeout,
    )
    answer = text_of(second)
    if second.get("stop_reason") != "end_turn":
        raise CheckError(f"the resumed turn stopped at {second.get('stop_reason')!r}")
    if not answer:
        raise CheckError("the resumed turn has no text answer")
    if _RESULT_NONCE not in answer.lower():
        raise CheckError(
            f"the resumed turn did not use the tool result: {answer[:300]!r}"
        )


def _check_tool_set_change(
    base: str,
    key: str | None,
    session: str,
    model: str,
    timeout: float,
) -> None:
    """A tool added between requests must be callable, not just answered."""
    prompt = "Call the noop tool. Do not answer in text."
    first = _messages(
        base,
        key,
        session,
        {
            "model": model,
            "max_tokens": 256,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [ECHO, NOOP],
        },
        timeout,
    )
    if first.get("stop_reason") != "tool_use":
        raise CheckError(
            "the changed tool set did not expose noop; the turn stopped at "
            f"{first.get('stop_reason')!r}: {text_of(first)[:300]!r}"
        )
    call = tool_use_of(first)
    if call.get("name") != NOOP["name"]:
        raise CheckError(
            f"the changed tool set called {call.get('name')!r}, not 'noop'"
        )

    second = _messages(
        base,
        key,
        session,
        {
            "model": model,
            "max_tokens": 256,
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": first["content"]},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": call["id"],
                            "content": "ok",
                        }
                    ],
                },
            ],
            "tools": [ECHO, NOOP],
        },
        timeout,
    )
    if second.get("stop_reason") != "end_turn":
        raise CheckError(
            f"the changed-set result stopped at {second.get('stop_reason')!r}"
        )
    if not text_of(second):
        raise CheckError("the changed-set result produced no text answer")


def quota_summary(payload: dict[str, Any]) -> str:
    """Summarise every credential reading; fail only when none is good.

    A lane may hold several credentials for rotation, so one exhausted
    credential is not a broken lane.  Every entry is still reported: a bad
    one becomes a ``[warn]`` in the output instead of a silent skip.
    """
    if payload.get("status") != "ok":
        raise CheckError(
            f"quota is {payload.get('status')!r}: "
            f"{payload.get('reason') or 'no reason'}"
        )
    entries = payload.get("credentials")
    if not isinstance(entries, list) or not entries:
        raise CheckError("quota has no credential reading")
    lines: list[str] = []
    warnings: list[str] = []
    for index, entry in enumerate(entries):
        if isinstance(entry, dict):
            label = entry.get("credential") or f"credential {index}"
        else:
            label = f"credential {index}"
        reading = entry.get("reading") if isinstance(entry, dict) else None
        if not isinstance(reading, dict) or reading.get("status") != "ok":
            warnings.append(f"{label}: no good reading")
            continue
        windows = reading.get("windows")
        if not isinstance(windows, list) or not windows:
            warnings.append(f"{label}: no windows")
            continue
        detail = ", ".join(
            f"{window.get('name')} {window.get('used_percent')}%"
            for window in windows
            if isinstance(window, dict)
        )
        lines.append(f"{label}: {detail}")
    if not lines:
        raise CheckError(
            f"no credential has a quota reading ({'; '.join(warnings) or 'no entries'})"
        )
    summary = "; ".join(lines)
    if warnings:
        summary += " [warn] " + "; ".join(warnings)
    return summary


def _check_quota(
    base: str, provider: str, admin_key: str | None, timeout: float
) -> str:
    headers = {"x-admin-token": admin_key} if admin_key else {}
    payload = _request(
        f"{base}/admin/api/config/providers/{provider}/quota",
        headers=headers,
        timeout=timeout,
    )
    return quota_summary(payload)


def _image_block(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    media = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(suffix)
    if media is None:
        raise CheckError(f"unsupported image suffix: {path.suffix}")
    size = path.stat().st_size
    if size > _MAX_IMAGE_BYTES:
        raise CheckError(
            f"{path} is {size} bytes; the image limit is {_MAX_IMAGE_BYTES}"
        )
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media,
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        },
    }


def _check_image(
    base: str,
    key: str | None,
    session: str,
    model: str,
    image: Path,
    timeout: float,
) -> str:
    payload = _messages(
        base,
        key,
        session,
        {
            "model": model,
            "max_tokens": 256,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        _image_block(image),
                        {
                            "type": "text",
                            "text": "Describe this image in one sentence.",
                        },
                    ],
                }
            ],
        },
        timeout,
    )
    answer = text_of(payload)
    if not answer:
        raise CheckError("the image turn produced no text answer")
    return answer


def _step(name: str, detail: str) -> None:
    print(f"ok   {name}: {detail}", flush=True)


def main(argv: list[str] | None = None) -> int:
    """Run the checks; return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key", default=os.environ.get("GATEWAY_API_KEY"))
    parser.add_argument(
        "--admin-key",
        default=os.environ.get("GATEWAY_ADMIN_KEY"),
        help="the gateway's internal admin token (sent as x-admin-token)",
    )
    parser.add_argument("--session", default=f"live-acp-check-{int(time.time())}")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--no-quota", action="store_true")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args(argv)
    base = args.base_url.rstrip("/")

    try:
        _check_models(base, args.api_key, args.provider, args.model, args.timeout)
        _step("models", args.model)
        count = _check_count_tokens(
            base, args.api_key, args.session, args.model, args.timeout
        )
        _step("count_tokens", f"{count} tokens (estimate or upstream)")
        _check_tool_round_trip(
            base, args.api_key, args.session, args.model, args.timeout
        )
        _step("tool call", "tool_use returned and the result resumed the turn")
        _check_tool_set_change(
            base, args.api_key, args.session, args.model, args.timeout
        )
        _step("tool set change", "a tool added between requests is callable")
        if not args.no_quota:
            windows = _check_quota(base, args.provider, args.admin_key, args.timeout)
            _step("quota", windows)
        if args.image is not None:
            answer = _check_image(
                base,
                args.api_key,
                args.session,
                args.model,
                args.image,
                args.timeout,
            )
            _step("image", answer[:120])
    except CheckError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print("all checks passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
