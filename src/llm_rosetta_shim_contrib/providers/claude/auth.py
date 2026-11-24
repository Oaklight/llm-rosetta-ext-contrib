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

The executable is the one the ACP agent will use.  The adapter pins a Claude
Code build and installs it under the lane's ``npm_config_cache``, so that
bundled binary is preferred: a gateway image needs Node.js and npx, not a
global ``claude`` install, and the sign-in writes to the store the same build
reads.  ``CLAUDE_CODE_EXECUTABLE`` in ``acp_env`` overrides it for operators
who run a different build; otherwise ``claude`` on the gateway's ``PATH`` is
the last resort.  Before the adapter has been installed there is no bundled
binary and the lane must already have ``claude`` or an override, or the panel
reports which one to install.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import threading
import time
from typing import Any

from llm_rosetta.contracts.auth import (
    AuthContext,
    AuthExchangeError,
    BaseAuthExchange,
)

try:
    from llm_rosetta_shim_contrib._vendor_cli import (
        CliLoginError,
        begin_cli_login,
        complete_cli_login,
        run_capture,
        subprocess_env,
    )
except ModuleNotFoundError as exc:  # a manifest archive ships the helper itself
    if exc.name != "llm_rosetta_shim_contrib":
        raise
    import importlib.util

    from pathlib import Path

    _helper = next(
        (
            parent / "_vendor_cli.py"
            for parent in Path(__file__).resolve().parents
            if (parent / "_vendor_cli.py").is_file()
        ),
        None,
    )
    if _helper is None:
        raise ModuleNotFoundError(
            "providers/_vendor_cli.py is missing from this archive",
            name="llm_rosetta_shim_contrib._vendor_cli",
        ) from exc
    _spec = importlib.util.spec_from_file_location("_vendor_cli", _helper)
    if _spec is None or _spec.loader is None:
        raise RuntimeError(f"cannot load {_helper}") from exc
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    CliLoginError = _module.CliLoginError
    begin_cli_login = _module.begin_cli_login
    complete_cli_login = _module.complete_cli_login
    run_capture = _module.run_capture
    subprocess_env = _module.subprocess_env

#: The CLI's own status is cheap but spawning it twice for one panel render is
#: still wasteful; a short cache keeps the two calls consistent as well.
STATUS_TTL = 2.0
_STATUS_LOCK = threading.Lock()
_STATUS_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}

#: Variables the gateway's own environment may carry that outrank the stored
#: Claude Code login.  ``ANTHROPIC_API_KEY`` switches the CLI to API billing,
#: and ``ANTHROPIC_BASE_URL``/``ANTHROPIC_MODEL`` point it at another host or
#: model; either would make the panel's sign-in report a different account
#: from the one the agent uses.  The shim's ``acp_env_unset`` declares the same
#: names; ``tests/claude/test_registration.py`` asserts they match.
CLAUDE_ENV_UNSET: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
)


def _acp_env(ctx: AuthContext) -> dict[str, str]:
    """The ``acp_env`` map the provider entry declares, if any."""
    raw = (ctx.config or {}).get("acp_env")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def _cli_env(ctx: AuthContext) -> dict[str, str]:
    """The sign-in CLI's environment, matching what the ACP agent receives."""
    return subprocess_env(_acp_env(ctx), CLAUDE_ENV_UNSET)


#: The npx cache the shim gives the adapter holds one directory per install,
#: and the SDK publishes its CLI in a platform package there.
_BUNDLED_CLI_GLOBS = (
    "_npx/*/node_modules/@anthropic-ai/claude-agent-sdk-*/claude",
    "_npx/*/node_modules/@anthropic-ai/claude-agent-sdk-*/claude.exe",
)


def _bundled_executable(ctx: AuthContext) -> str:
    """The Claude Code build the adapter installed in the lane's npm cache.

    The adapter is started with ``npm_config_cache={acp_home}/npm``, so this is
    the binary that will serve the lane's requests.  Its credential store is
    the same ``CLAUDE_CONFIG_DIR``.  Empty when the adapter has not run yet.
    """
    cache = _acp_env(ctx).get("npm_config_cache")
    if not cache:
        return ""
    newest: tuple[float, str] | None = None
    for pattern in _BUNDLED_CLI_GLOBS:
        for path in glob.glob(os.path.join(cache, pattern)):
            if not os.access(path, os.X_OK):
                continue
            try:
                modified = os.stat(path).st_mtime
            except OSError:
                continue
            if newest is None or modified > newest[0]:
                newest = (modified, path)
    return newest[1] if newest else ""


def _executable(ctx: AuthContext) -> str:
    """The Claude Code binary to drive, or a clear operator-facing error."""
    custom = _acp_env(ctx).get("CLAUDE_CODE_EXECUTABLE")
    if custom:
        return custom
    bundled = _bundled_executable(ctx)
    if bundled:
        return bundled
    found = shutil.which("claude")
    if found:
        return found
    raise AuthExchangeError(
        "no Claude Code CLI is available for the admin sign-in: the adapter "
        "has not been installed in this lane's npm cache yet, and `claude` is "
        "not on the gateway's PATH.  Send one request through the lane first, "
        "or install Claude Code, or set CLAUDE_CODE_EXECUTABLE in this "
        "provider's acp_env"
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
            env=_cli_env(ctx),
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
    """What the panel may show: account, method and profile, never a token."""
    method = str(data.get("authMethod") or "")
    email = data.get("email")
    email = email if isinstance(email, str) and email else ""
    if method == "claude.ai":
        subject = (
            f"{email} (Claude subscription)"
            if email
            else "Claude subscription (claude.ai)"
        )
    elif method in ("api_key", "api_key_helper"):
        subject = (
            f"{email} (Anthropic API billing, {method})"
            if email
            else f"Anthropic API billing ({method})"
        )
    else:
        subject = (
            f"{email} (Claude Code)"
            if email
            else f"Claude Code ({method or 'signed in'})"
        )
    summary: dict[str, Any] = {
        "connected": True,
        "subject": subject,
        "auth_method": method,
    }
    if email:
        # The account an operator recognizes.  It is not a credential; the
        # CLI reports it for exactly this purpose.
        summary["email"] = email
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
        """The signed-in address, so two entries name different accounts.

        The CLI's status is the only source: the gateway holds no token and
        the adapter's store is opaque.  A missing address stays ``None``
        rather than guessing from the profile path.
        """
        data = _status(ctx) or {}
        email = data.get("email")
        return email if isinstance(email, str) and email else None

    def describe(self, ctx: AuthContext) -> dict[str, Any] | None:
        """Report who is signed in, from the CLI's own status."""
        data = _status(ctx)
        if not _signed_in(data):
            return None
        return _summary(ctx, data or {})

    def begin_login(self, ctx: AuthContext) -> dict[str, Any]:
        """Run ``claude auth login --claudeai`` and return its URL.

        The CLI is given a browser recorder, so it does not open a tab beside
        the one the admin panel shows: the panel's page is the only one the
        operator sees, and its paste box is the only way the flow finishes.
        The recorder also learns the CLI's loopback port, so a pasted callback
        URL can be replayed here instead of typed into the CLI.
        """
        executable = _executable(ctx)
        try:
            return begin_cli_login(
                ctx.provider,
                [executable, "auth", "login", "--claudeai"],
                env=_cli_env(ctx),
                paste_label=(
                    "Paste the code the Claude page shows, or the full callback URL"
                ),
                paste_placeholder="the code shown after signing in",
                browser=True,
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
            env=_cli_env(ctx),
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
