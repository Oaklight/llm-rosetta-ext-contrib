"""The Claude ACP lane's vendor-managed sign-in exchange.

The exchange drives a fake ``claude`` binary through the same sequence the
real CLI uses: print an authorization URL, wait for a pasted code, then answer
``auth status --json``.  Nothing here touches a real account.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

import pytest

from llm_rosetta.contracts.auth import AuthContext, AuthExchangeError

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "llm_rosetta_shim_contrib"
    / "providers"
    / "claude"
    / "auth.py"
)

FAKE_CLI = """#!/usr/bin/env python3
import json, os, sys

args = sys.argv[1:]
state = os.environ["FAKE_STATE"]

if "status" in args:
    if os.path.exists(state):
        print(open(state, encoding="utf-8").read())
    else:
        print(json.dumps({"loggedIn": False}))
    sys.exit(0)

if "login" in args:
    browser = os.environ.get("BROWSER")
    if browser:
        import subprocess
        subprocess.run(
            [browser, "http://127.0.0.1:45109/callback?code=good&state=s"],
            check=False,
        )
    print("If the browser didn't open, visit: "
          "https://claude.com/cai/oauth/authorize?code=true&state=x")
    print("Paste code here if prompted > ", end="", flush=True)
    line = sys.stdin.readline().strip()
    if line not in ("good-code", "good-code#state"):
        print("the code was refused: " + line)
        sys.exit(1)
    with open(state, "w", encoding="utf-8") as handle:
        json.dump({"loggedIn": True, "authMethod": "claude.ai",
                   "email": "test@example.com",
                   "apiProvider": "firstParty",
                   "configDirectory": os.environ.get("CLAUDE_CONFIG_DIR")
                   or "/home/pding/.claude"}, handle)
    sys.exit(0)

if "logout" in args:
    try:
        os.unlink(state)
    except FileNotFoundError:
        pass
    sys.exit(0)

sys.exit(2)
"""


@pytest.fixture(scope="module")
def exchange_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("claude_auth_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    script = tmp_path / "claude"
    script.write_text(FAKE_CLI, encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("FAKE_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "profile"))
    return script


@pytest.fixture(autouse=True)
def _fresh_status(exchange_module: ModuleType):
    exchange_module._STATUS_CACHE.clear()
    yield
    exchange_module._STATUS_CACHE.clear()


def _ctx(script: Path) -> AuthContext:
    return AuthContext(
        provider="claude",
        config={
            "acp_env": {
                "CLAUDE_CODE_EXECUTABLE": str(script),
                "CLAUDE_CONFIG_DIR": "/tmp/claude-profile",
            }
        },
    )


def test_the_exchange_is_vendor_managed(exchange_module: ModuleType):
    exchange = exchange_module.EXCHANGE

    assert exchange.vendor_managed is True
    assert exchange.kind == "vendor-cli"


def test_the_gateways_billing_environment_is_not_passed_to_the_cli(
    exchange_module, cli: Path, monkeypatch: pytest.MonkeyPatch
):
    """A gateway ANTHROPIC_API_KEY would switch Claude Code to API billing."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-gateway")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://gateway.example")

    env = exchange_module._cli_env(_ctx(cli))

    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_BASE_URL" not in env
    assert env["CLAUDE_CODE_EXECUTABLE"] == str(cli)


def test_status_drives_needs_setup_and_the_summary(exchange_module, cli: Path):
    exchange = exchange_module.EXCHANGE
    ctx = _ctx(cli)

    assert exchange.needs_interactive_setup(ctx) is True
    assert exchange.describe(ctx) is None

    Path(os.environ["FAKE_STATE"]).write_text(
        json.dumps(
            {
                "loggedIn": True,
                "authMethod": "claude.ai",
                "email": "test@example.com",
                "apiProvider": "firstParty",
                "configDirectory": "/tmp/claude-profile",
            }
        ),
        encoding="utf-8",
    )
    exchange_module._STATUS_CACHE.clear()

    assert exchange.needs_interactive_setup(ctx) is False
    summary = exchange.describe(ctx)
    assert summary is not None
    assert summary["subject"] == "test@example.com (Claude subscription)"
    assert summary["email"] == "test@example.com"
    assert summary["config_directory"] == "/tmp/claude-profile"
    assert exchange.account_id(ctx) == "test@example.com"


def test_begin_returns_the_cli_url_and_no_token(exchange_module, cli: Path):
    started = exchange_module.EXCHANGE.begin_login(_ctx(cli))

    assert started["authorization_url"].startswith("https://claude.com/cai/oauth/")
    assert started["callback_origin"] == "http://127.0.0.1:45109"
    assert started["paste_label"]
    assert "access_token" not in started
    assert "refresh_token" not in started


def test_complete_accepts_the_code_with_its_state(exchange_module, cli: Path):
    exchange = exchange_module.EXCHANGE
    ctx = _ctx(cli)
    exchange.begin_login(ctx)

    summary = exchange.complete_login(ctx, "good-code#state")

    assert summary["subject"] == "test@example.com (Claude subscription)"


def test_a_callback_from_another_port_is_refused(exchange_module, cli: Path):
    exchange = exchange_module.EXCHANGE
    ctx = _ctx(cli)
    exchange.begin_login(ctx)

    with pytest.raises(AuthExchangeError, match="isn't from this sign-in"):
        exchange.complete_login(ctx, "http://127.0.0.1:1/callback?code=x")


def test_the_adapters_bundled_cli_is_preferred(
    exchange_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("FAKE_STATE", str(tmp_path / "state.json"))
    bundled = (
        tmp_path
        / "npm"
        / "_npx"
        / "abc"
        / "node_modules"
        / "@anthropic-ai"
        / "claude-agent-sdk-linux-x64"
        / "claude"
    )
    bundled.parent.mkdir(parents=True)
    bundled.write_text(FAKE_CLI, encoding="utf-8")
    bundled.chmod(0o755)
    ctx = AuthContext(
        provider="claude",
        config={
            "acp_env": {
                "CLAUDE_CONFIG_DIR": str(tmp_path / "profile"),
                "npm_config_cache": str(tmp_path / "npm"),
            }
        },
    )

    assert exchange_module._executable(ctx) == str(bundled)
    assert exchange_module.EXCHANGE.needs_interactive_setup(ctx) is True


def test_complete_passes_the_code_and_verifies_status(exchange_module, cli: Path):
    exchange = exchange_module.EXCHANGE
    ctx = _ctx(cli)
    exchange.begin_login(ctx)

    summary = exchange.complete_login(ctx, "good-code")

    assert summary["subject"] == "test@example.com (Claude subscription)"
    assert summary["email"] == "test@example.com"
    assert exchange.needs_interactive_setup(ctx) is False


def test_a_refused_code_is_reported_without_echoing_it(exchange_module, cli: Path):
    exchange = exchange_module.EXCHANGE
    ctx = _ctx(cli)
    exchange.begin_login(ctx)

    with pytest.raises(AuthExchangeError) as raised:
        exchange.complete_login(ctx, "bad-code")

    assert "exited with 1" in str(raised.value)
    assert "bad-code" not in str(raised.value)
    assert "<redacted>" in str(raised.value)


def test_revoke_signs_the_cli_out(exchange_module, cli: Path):
    exchange = exchange_module.EXCHANGE
    ctx = _ctx(cli)
    exchange.begin_login(ctx)
    exchange.complete_login(ctx, "good-code")
    assert exchange.needs_interactive_setup(ctx) is False

    revoked = exchange.revoke(ctx)

    assert revoked is False
    assert exchange.needs_interactive_setup(ctx) is True


def test_the_exchange_never_mints_a_credential(exchange_module, cli: Path):
    import asyncio

    with pytest.raises(AuthExchangeError, match="never mints"):
        asyncio.run(exchange_module.EXCHANGE.credential(_ctx(cli)))


def test_a_missing_cli_is_reported_to_the_operator(
    exchange_module, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(exchange_module.shutil, "which", lambda name: None)
    ctx = AuthContext(provider="claude", config={})

    with pytest.raises(AuthExchangeError, match="CLAUDE_CODE_EXECUTABLE"):
        exchange_module.EXCHANGE.begin_login(ctx)
