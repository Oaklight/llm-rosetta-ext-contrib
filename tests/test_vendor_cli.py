"""The shared CLI sign-in driver used by the vendor-managed exchanges.

Every test runs a real child process: the point of the helper is that it
survives a CLI that prints a URL, waits on stdin, and then either accepts or
rejects the pasted value.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from llm_rosetta_shim_contrib._vendor_cli import (
    CliLoginError,
    begin_cli_login,
    cancel_cli_login,
    complete_cli_login,
)

FAKE_CLI = """
import json, os, sys

args = sys.argv[1:]
state = os.environ["FAKE_STATE"]

if "login" in args:
    print("Opening browser to sign in…")
    print("\\x1b]8;;https://accounts.example/oauth2/auth?state=abc\\x1b\\\\"
          "https://accounts.example/oauth2/auth?state=abc\\x1b]8;;\\x1b\\\\")
    print("Paste code here if prompted > ", end="", flush=True)
    line = sys.stdin.readline().strip()
    if line != "good-code":
        print("the code was refused: " + line)
        sys.exit(3)
    with open(state, "w", encoding="utf-8") as handle:
        handle.write('{"loggedIn": true, "authMethod": "claude.ai"}')
    sys.exit(0)

if "logout" in args:
    try:
        os.unlink(state)
    except FileNotFoundError:
        pass
    sys.exit(0)
"""


@pytest.fixture()
def fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    script = tmp_path / "fake_cli.py"
    script.write_text(FAKE_CLI, encoding="utf-8")
    monkeypatch.setenv("FAKE_STATE", str(tmp_path / "signed-in.json"))
    return [sys.executable, str(script)]


def test_begin_returns_the_url_and_not_the_escape_wrapper(fake_cli):
    key = "test-claude"
    try:
        started = begin_cli_login(key, fake_cli + ["login"])
    finally:
        cancel_cli_login(key)

    assert (
        started["authorization_url"] == "https://accounts.example/oauth2/auth?state=abc"
    )
    assert started["expires_at"] > 0
    assert "Paste" in started["paste_label"]


def test_complete_writes_the_code_and_the_cli_exits_zero(fake_cli):
    key = "test-claude-complete"
    begin_cli_login(key, fake_cli + ["login"])

    complete_cli_login(key, "good-code")

    import os

    assert Path(os.environ["FAKE_STATE"]).exists()


def test_a_refused_code_is_reported_and_redacted(fake_cli):
    key = "test-claude-refused"
    begin_cli_login(key, fake_cli + ["login"])

    with pytest.raises(CliLoginError) as raised:
        complete_cli_login(key, "bad-code")

    assert "exited with 3" in str(raised.value)
    assert "bad-code" not in str(raised.value)
    assert "<redacted>" in str(raised.value)


def test_completing_without_a_pending_sign_in_is_an_error():
    with pytest.raises(CliLoginError, match="no sign-in is pending"):
        complete_cli_login("never-started", "code")


def test_an_empty_code_is_refused_before_the_process_is_touched(fake_cli):
    key = "test-claude-empty"
    begin_cli_login(key, fake_cli + ["login"])
    try:
        with pytest.raises(CliLoginError, match="code or callback URL"):
            complete_cli_login(key, "   \n")
    finally:
        cancel_cli_login(key)


def test_the_error_says_what_a_cli_that_exits_early_printed(tmp_path: Path):
    script = tmp_path / "dies.py"
    script.write_text(
        "import sys\nprint('no credentials file at ~/.tool/auth.json')\nsys.exit(2)\n",
        encoding="utf-8",
    )

    with pytest.raises(CliLoginError) as raised:
        begin_cli_login("dies-early", [sys.executable, str(script)])

    message = str(raised.value)
    assert "no authorization URL" in message
    assert "no credentials file" in message


def test_starting_again_replaces_the_previous_process(fake_cli):
    key = "test-claude-supersede"
    first = begin_cli_login(key, fake_cli + ["login"])
    second = begin_cli_login(key, fake_cli + ["login"])
    try:
        assert first["authorization_url"] == second["authorization_url"]
        # The first process is gone, so its value can no longer complete.
        complete_cli_login(key, "good-code")
    finally:
        cancel_cli_login(key)


def test_a_command_that_prints_no_url_fails_fast(tmp_path, monkeypatch):
    script = tmp_path / "silent.py"
    script.write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
    with pytest.raises(CliLoginError, match="printed no authorization URL"):
        begin_cli_login("silent", [sys.executable, str(script)], url_timeout=5)


def test_a_missing_command_is_an_error_not_a_crash(tmp_path):
    with pytest.raises(CliLoginError, match="could not start"):
        begin_cli_login("missing", [str(tmp_path / "no-such-binary")])
