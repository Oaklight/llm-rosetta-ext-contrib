"""The Antigravity lane's vendor-managed sign-in exchange.

``agy`` owns the Google account; the exchange only drives ``agy acp --login``
and reads the account summary from the keyring entry.  The keyring is faked,
and the CLI is a small script that prints a URL and waits for a code.
"""

from __future__ import annotations

import importlib.util
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from llm_rosetta.contracts.auth import AuthContext, AuthExchangeError

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "llm_rosetta_shim_contrib"
    / "providers"
    / "antigravity"
    / "auth.py"
)

FAKE_CLI = """#!/usr/bin/env python3
import sys

args = sys.argv[1:]
if "--login" in args:
    print("Open this link in a browser to log in with Google:")
    print()
    print("  https://accounts.google.com/o/oauth2/auth?state=abc")
    print()
    print("Then paste the authorization code, or the full URL of the page "
          "you land on, and press Enter:")
    sys.stdout.flush()
    line = sys.stdin.readline().strip()
    if line != "good-code":
        print("the code was refused: " + line)
        sys.exit(1)
    sys.exit(0)
sys.exit(2)
"""

RECORD = {
    "auth_method": "consumer",
    "id_token_email": "person@example.com",
    "token": {
        "access_token": "must-not-escape",
        "refresh_token": "must-not-escape",
        "expiry": "2026-11-22T22:54:34.220251492-06:00",
    },
}


@pytest.fixture(scope="module")
def exchange_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "antigravity_auth_under_test", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def cli(tmp_path: Path) -> Path:
    script = tmp_path / "agy"
    script.write_text(FAKE_CLI, encoding="utf-8")
    script.chmod(0o755)
    return script


def _ctx(script: Path, home: str | None = None) -> AuthContext:
    config: dict[str, Any] = {"acp_argv": [str(script)]}
    if home is not None:
        config["acp_env"] = {"LLM_ROSETTA_ACP_HOME": home}
    return AuthContext(provider="antigravity", config=config)


def _record(module: ModuleType, monkeypatch: pytest.MonkeyPatch, record) -> None:
    """Fake a readable keyring whose only entry is *record* (or nothing)."""
    monkeypatch.setattr(module, "_keyring_available", lambda: True)
    monkeypatch.setattr(module, "_read_account", lambda: record)


def _no_keyring(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake a host with no libsecret, where the CLI is the only authority."""
    monkeypatch.setattr(module, "_keyring_available", lambda: False)
    monkeypatch.setattr(module, "_read_account", lambda: None)


def test_the_exchange_is_vendor_mediated_and_not_revocable(exchange_module):
    exchange = exchange_module.EXCHANGE

    assert exchange.vendor_managed is True
    assert exchange.kind == "vendor-cli"
    assert exchange.can_revoke() is False


def test_the_status_record_drives_the_summary(exchange_module, monkeypatch):
    _record(exchange_module, monkeypatch, None)
    exchange = exchange_module.EXCHANGE
    ctx = AuthContext(provider="antigravity", config={})

    assert exchange.needs_interactive_setup(ctx) is True
    assert exchange.describe(ctx) is None
    assert exchange.account_id(ctx) is None

    _record(exchange_module, monkeypatch, RECORD)

    assert exchange.needs_interactive_setup(ctx) is False
    assert exchange.account_id(ctx) == "person@example.com"
    summary = exchange.describe(ctx)
    assert summary is not None
    assert summary["subject"] == "person@example.com (Google account)"
    assert "access_token" not in summary
    assert "must-not-escape" not in repr(summary)
    expected = datetime(
        2026, 11, 22, 22, 54, 34, 220251, tzinfo=timezone(timedelta(hours=-6))
    ).timestamp()
    assert abs(summary["expires_at"] - expected) < 0.001


def test_begin_returns_the_google_url(exchange_module, cli: Path):
    started = exchange_module.EXCHANGE.begin_login(_ctx(cli))

    assert started["authorization_url"].startswith(
        "https://accounts.google.com/o/oauth2/auth"
    )
    assert started["paste_label"]


def test_login_runs_in_the_lanes_persistent_profile(exchange_module, cli: Path):
    """The login must write the store the ACP agent will later read."""
    ctx = _ctx(cli, home="/data/acp/antigravity")

    assert exchange_module._login_argv(ctx) == [
        str(cli),
        "acp",
        "--login",
        "--gemini-dir",
        "/data/acp/antigravity",
    ]


def test_login_without_a_home_leaves_the_flag_out(exchange_module, cli: Path):
    """A host that names no home keeps the CLI's own default."""
    assert exchange_module._login_argv(_ctx(cli)) == [str(cli), "acp", "--login"]


def test_complete_waits_for_the_keyring_and_returns_the_account(
    exchange_module, cli: Path, monkeypatch
):
    exchange = exchange_module.EXCHANGE
    ctx = _ctx(cli)
    exchange.begin_login(ctx)
    _record(exchange_module, monkeypatch, RECORD)

    summary = exchange.complete_login(ctx, "good-code")

    assert summary["subject"] == "person@example.com (Google account)"


def test_complete_succeeds_without_a_readable_keyring(
    exchange_module, cli: Path, monkeypatch, tmp_path
):
    exchange = exchange_module.EXCHANGE
    ctx = _ctx(cli, home=str(tmp_path / "home"))
    exchange.begin_login(ctx)
    _no_keyring(exchange_module, monkeypatch)

    summary = exchange.complete_login(ctx, "good-code")

    assert summary["connected"] is True
    assert "Google account" in summary["subject"]
    marker = tmp_path / "home" / exchange_module.LOGIN_MARKER
    assert marker.is_file()
    assert "must-not-escape" not in marker.read_text(encoding="utf-8")
    assert stat.S_IMODE(marker.stat().st_mode) == 0o600
    # A later render must not send the operator through setup again.
    assert exchange.describe(ctx) is not None
    assert exchange.needs_interactive_setup(ctx) is False


def test_a_finished_headless_login_is_scoped_to_its_home(
    exchange_module, cli: Path, monkeypatch, tmp_path
):
    exchange = exchange_module.EXCHANGE
    first = _ctx(cli, home=str(tmp_path / "one"))
    exchange.begin_login(first)
    _no_keyring(exchange_module, monkeypatch)
    exchange.complete_login(first, "good-code")

    other = _ctx(cli, home=str(tmp_path / "two"))

    assert exchange.describe(other) is None
    assert exchange.needs_interactive_setup(other) is True


def test_a_refused_code_is_reported_without_echoing_it(
    exchange_module, cli: Path, monkeypatch
):
    exchange = exchange_module.EXCHANGE
    ctx = _ctx(cli)
    exchange.begin_login(ctx)
    _record(exchange_module, monkeypatch, RECORD)

    with pytest.raises(AuthExchangeError) as raised:
        exchange.complete_login(ctx, "bad-code")

    assert "exited with 1" in str(raised.value)
    assert "bad-code" not in str(raised.value)
    assert "<redacted>" in str(raised.value)


def test_the_exchange_never_mints_a_credential(exchange_module, cli: Path):
    import asyncio

    with pytest.raises(AuthExchangeError, match="never mints"):
        asyncio.run(exchange_module.EXCHANGE.credential(_ctx(cli)))


def test_epoch_tolerates_nanoseconds(exchange_module):
    expected = datetime(
        2026, 11, 22, 22, 54, 34, 220251, tzinfo=timezone(timedelta(hours=-6))
    ).timestamp()

    assert abs(exchange_module._epoch(RECORD["token"]["expiry"]) - expected) < 0.001
    assert exchange_module._epoch("not a time") is None
