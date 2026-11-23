"""Sign in to Antigravity through the ``agy`` CLI.

The Antigravity ACP lane is keyless: ``agy`` authenticates itself and the
gateway never sees the token.  On Linux the token lives in the desktop
keyring as one entry for the whole installation (``service=gemini``,
``user=antigravity``), not in the ``--gemini-dir`` profile the transport
hardens, so every provider of this shim shares one Google account.

This exchange is therefore **vendor-managed**: it keeps the lane keyless and
never mints or seeds a credential.  It drives ``agy acp --login``, returns the
Google URL that command prints, writes the pasted code back, and reports the
account the CLI wrote to the keyring.  The token itself is never read into the
gateway's credential ring and never appears in a response.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from datetime import datetime
from typing import Any

from llm_rosetta.contracts.auth import (
    AuthContext,
    AuthExchangeError,
    BaseAuthExchange,
)

from llm_rosetta_shim_contrib._vendor_cli import (
    CliLoginError,
    begin_cli_login,
    complete_cli_login,
    run_capture,
    subprocess_env,
)

#: The keyring entry ``agy`` writes.  Measured on agy 1.5.14.
KEYRING_SERVICE = "gemini"
KEYRING_USER = "antigravity"

#: How long the keyring may lag behind the CLI's exit.
KEYRING_WAIT = 10.0


def _acp_env(ctx: AuthContext) -> dict[str, str]:
    raw = (ctx.config or {}).get("acp_env")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def _executable(ctx: AuthContext) -> str:
    """The ``agy`` binary the provider starts, or a clear error."""
    argv = (ctx.config or {}).get("acp_argv")
    if isinstance(argv, (list, tuple)) and argv:
        first = str(argv[0])
        if first:
            return first
    found = shutil.which("agy")
    if found:
        return found
    raise AuthExchangeError(
        "the `agy` CLI is not on the gateway's PATH, so the admin sign-in "
        "cannot drive it; install Antigravity CLI or set this provider's "
        "acp_argv to its path"
    )


def _keyring_available() -> bool:
    return shutil.which("secret-tool") is not None


def _read_account() -> dict[str, Any] | None:
    """The signed-in account record, without its token.

    ``None`` means "no account, or the keyring cannot be read".  Callers ask
    :func:`_keyring_available` when the two must be told apart.
    """
    if not _keyring_available():
        return None
    captured = run_capture(
        [
            "secret-tool",
            "lookup",
            "service",
            KEYRING_SERVICE,
            "username",
            KEYRING_USER,
        ],
        timeout=10.0,
    )
    if captured is None:
        return None
    code, stdout, _ = captured
    if code != 0 or not stdout.strip():
        return None
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


_RFC3339 = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(.*)$")


def _epoch(text: Any) -> float | None:
    """An RFC 3339 timestamp as epoch seconds, tolerating nanoseconds."""
    if not isinstance(text, str):
        return None
    match = _RFC3339.match(text.strip())
    if match is None:
        return None
    fraction = (match.group(2) or "")[:6].ljust(6, "0")
    try:
        parsed = datetime.fromisoformat(f"{match.group(1)}.{fraction}{match.group(3)}")
    except ValueError:
        return None
    try:
        return parsed.timestamp()
    except (OverflowError, OSError):
        return None


def _summary(data: dict[str, Any]) -> dict[str, Any]:
    email = data.get("id_token_email")
    subject = (
        f"{email} (Google account)"
        if isinstance(email, str) and email
        else "Antigravity (Google account)"
    )
    summary: dict[str, Any] = {
        "connected": True,
        "subject": subject,
        "auth_method": str(data.get("auth_method") or ""),
    }
    token = data.get("token")
    expiry = _epoch(token.get("expiry")) if isinstance(token, dict) else None
    if expiry is not None:
        summary["expires_at"] = expiry
    return summary


class AntigravityCliExchange(BaseAuthExchange):
    """Drive ``agy``'s own Google sign-in from the admin panel."""

    kind = "vendor-cli"
    consumes_key = False
    vendor_managed = True

    def needs_interactive_setup(self, ctx: AuthContext) -> bool:
        """Whether the keyring holds no account this host can see."""
        if not _keyring_available():
            # No libsecret here: the CLI may still be signed in, and claiming
            # otherwise would offer a button that cannot verify its result.
            return False
        return _read_account() is None

    async def credential(self, ctx: AuthContext) -> str:
        """Refuse: the gateway never holds this lane's credential."""
        raise AuthExchangeError(
            "the Antigravity CLI owns this credential; the gateway never mints it"
        )

    def account_id(self, ctx: AuthContext) -> str | None:
        """The signed-in Google address, when the keyring exposes it."""
        data = _read_account() or {}
        email = data.get("id_token_email")
        return email if isinstance(email, str) and email else None

    def describe(self, ctx: AuthContext) -> dict[str, Any] | None:
        """Report the Google account and token expiry, never the token."""
        data = _read_account()
        return _summary(data) if data else None

    def begin_login(self, ctx: AuthContext) -> dict[str, Any]:
        """Run ``agy acp --login`` and return its Google URL."""
        executable = _executable(ctx)
        try:
            return begin_cli_login(
                ctx.provider,
                [executable, "acp", "--login"],
                env=subprocess_env(_acp_env(ctx)),
                paste_label=(
                    "Paste the authorization code, or the full URL of the page "
                    "you land on"
                ),
                paste_placeholder="the code or callback URL Google shows",
            )
        except CliLoginError as exc:
            raise AuthExchangeError(str(exc)) from exc

    def complete_login(self, ctx: AuthContext, callback_url: str) -> dict[str, Any]:
        """Feed the code to ``agy`` and wait for the keyring to show the account."""
        try:
            complete_cli_login(ctx.provider, callback_url)
        except CliLoginError as exc:
            raise AuthExchangeError(str(exc)) from exc
        if not _keyring_available():
            # The CLI exited 0 and this host cannot read the keyring; the CLI
            # is the authority on its own sign-in.
            return {"connected": True, "subject": "Antigravity (Google account)"}
        end = time.monotonic() + KEYRING_WAIT
        while time.monotonic() < end:
            data = _read_account()
            if data:
                return _summary(data)
            time.sleep(0.25)
        raise AuthExchangeError(
            "the Antigravity CLI exited but no account appeared in the keyring; "
            "run `agy acp --login` on the gateway host to see its own error"
        )


EXCHANGE = AntigravityCliExchange()
