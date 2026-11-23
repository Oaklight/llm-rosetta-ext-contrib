"""Sign in to Claude through the Claude Code CLI.

The Claude ACP lane does not hold a gateway credential.  The adapter starts
Claude Code, and Claude Code authenticates from its own store: ``~/.claude``
by default, or ``$CLAUDE_CONFIG_DIR`` when the provider's ``acp_env`` sets
one.  A Pro/Max subscription is written there by ``claude auth login
--claudeai``; ``--console`` signs in for API billing instead.

So this exchange is **vendor-managed**: it declares ``vendor_managed = True``,
which keeps the lane keyless and tells the gateway never to mint or seed a
token.  What it implements is the admin sign-in surface — start the CLI,
return the URL it prints, write the pasted code back, then report the CLI's
own ``auth status``.  The gateway sees no token and stores no record.

The executable is the one the ACP agent will use when the provider sets
``CLAUDE_CODE_EXECUTABLE`` in ``acp_env``; otherwise it is ``claude`` from the
gateway's ``PATH``.  The adapter bundles its own CLI, but the admin sign-in
needs a CLI binary to drive, so a host that installs only the adapter cannot
offer this button.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
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

#: The CLI's own status is cheap but spawning it twice for one panel render is
#: still wasteful; a short cache keeps the two calls consistent as well.
STATUS_TTL = 2.0
_STATUS_LOCK = threading.Lock()
_STATUS_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}


def _acp_env(ctx: AuthContext) -> dict[str, str]:
    """The ``acp_env`` map the provider entry declares, if any."""
    raw = (ctx.config or {}).get("acp_env")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def _executable(ctx: AuthContext) -> str:
    """The Claude Code binary to drive, or a clear operator-facing error."""
    custom = _acp_env(ctx).get("CLAUDE_CODE_EXECUTABLE")
    if custom:
        return custom
    found = shutil.which("claude")
    if found:
        return found
    raise AuthExchangeError(
        "the Claude Code CLI (`claude`) is not on the gateway's PATH, so the "
        "admin sign-in cannot drive it; install Claude Code, or set "
        "CLAUDE_CODE_EXECUTABLE in this provider's acp_env"
    )


def _status_key(ctx: AuthContext) -> str:
    env = _acp_env(ctx)
    return "\x00".join(
        (
            ctx.provider,
            env.get("CLAUDE_CODE_EXECUTABLE", ""),
            env.get("CLAUDE_CONFIG_DIR", ""),
        )
    )


def _status(ctx: AuthContext, *, refresh: bool = False) -> dict[str, Any] | None:
    """``claude auth status --json``, or ``None`` when it cannot be read.

    Never raises: a missing CLI or an unreadable store is an answer the panel
    can render as "needs setup", not a reason to fail the provider.
    """
    key = _status_key(ctx)
    now = time.time()
    if not refresh:
        with _STATUS_LOCK:
            hit = _STATUS_CACHE.get(key)
        if hit is not None and now - hit[0] < STATUS_TTL:
            return hit[1]
    result: dict[str, Any] | None = None
    try:
        executable = _executable(ctx)
    except AuthExchangeError:
        executable = ""
    if executable:
        captured = run_capture(
            [executable, "auth", "status", "--json"],
            env=subprocess_env(_acp_env(ctx)),
        )
        if captured is not None:
            code, stdout, _ = captured
            if code == 0:
                try:
                    parsed = json.loads(stdout)
                except ValueError:
                    parsed = None
                if isinstance(parsed, dict):
                    result = parsed
    with _STATUS_LOCK:
        _STATUS_CACHE[key] = (now, result)
    return result


def _signed_in(data: dict[str, Any] | None) -> bool:
    return bool(data and data.get("loggedIn"))


def _summary(ctx: AuthContext, data: dict[str, Any]) -> dict[str, Any]:
    """What the panel may show: method and profile, never a token."""
    method = str(data.get("authMethod") or "")
    if method == "claude.ai":
        subject = "Claude subscription (claude.ai)"
    elif method in ("api_key", "api_key_helper"):
        subject = f"Anthropic API billing ({method})"
    else:
        subject = f"Claude Code ({method or 'signed in'})"
    summary: dict[str, Any] = {
        "connected": True,
        "subject": subject,
        "auth_method": method,
    }
    provider = data.get("apiProvider")
    if isinstance(provider, str) and provider:
        summary["api_provider"] = provider
    config_dir = data.get("configDirectory") or _acp_env(ctx).get("CLAUDE_CONFIG_DIR")
    if isinstance(config_dir, str) and config_dir:
        summary["config_directory"] = config_dir
    return summary


class ClaudeCliExchange(BaseAuthExchange):
    """Drive Claude Code's own subscription sign-in from the admin panel."""

    kind = "vendor-cli"
    consumes_key = False
    vendor_managed = True

    def needs_interactive_setup(self, ctx: AuthContext) -> bool:
        """Whether the CLI reports no signed-in account."""
        return not _signed_in(_status(ctx))

    async def credential(self, ctx: AuthContext) -> str:
        """Refuse: the gateway never holds this lane's credential."""
        raise AuthExchangeError(
            "the Claude CLI owns this credential; the gateway never mints it"
        )

    def account_id(self, ctx: AuthContext) -> str | None:
        """Return ``None``: the CLI exposes no stable account identifier."""
        return None

    def describe(self, ctx: AuthContext) -> dict[str, Any] | None:
        """Report who is signed in, from the CLI's own status."""
        data = _status(ctx)
        if not _signed_in(data):
            return None
        return _summary(ctx, data or {})

    def begin_login(self, ctx: AuthContext) -> dict[str, Any]:
        """Run ``claude auth login --claudeai`` and return its URL."""
        executable = _executable(ctx)
        try:
            return begin_cli_login(
                ctx.provider,
                [executable, "auth", "login", "--claudeai"],
                env=subprocess_env(_acp_env(ctx)),
                paste_label=(
                    "Paste the code the Claude page shows, or the full callback URL"
                ),
                paste_placeholder="the code shown after signing in",
            )
        except CliLoginError as exc:
            raise AuthExchangeError(str(exc)) from exc

    def complete_login(self, ctx: AuthContext, callback_url: str) -> dict[str, Any]:
        """Feed the pasted code to the waiting CLI and verify the result."""
        try:
            complete_cli_login(ctx.provider, callback_url)
        except CliLoginError as exc:
            raise AuthExchangeError(str(exc)) from exc
        data = _status(ctx, refresh=True)
        if not _signed_in(data):
            raise AuthExchangeError(
                "the Claude CLI exited but does not report a signed-in account; "
                "run `claude auth status --json` on the gateway host"
            )
        return _summary(ctx, data or {})

    def revoke(self, ctx: AuthContext) -> bool:
        """Sign the CLI out locally; the vendor offers no revoke endpoint here."""
        executable = _executable(ctx)
        captured = run_capture(
            [executable, "auth", "logout"],
            env=subprocess_env(_acp_env(ctx)),
        )
        if captured is None:
            raise AuthExchangeError("the Claude CLI could not be run to sign out")
        code, stdout, stderr = captured
        if code != 0:
            detail = (stderr or stdout).strip()[:400]
            raise AuthExchangeError(
                f"the Claude CLI refused to sign out (exit {code}): {detail}"
            )
        with _STATUS_LOCK:
            _STATUS_CACHE.pop(_status_key(ctx), None)
        return False


EXCHANGE = ClaudeCliExchange()
