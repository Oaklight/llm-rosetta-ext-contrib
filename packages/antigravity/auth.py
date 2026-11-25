"""Sign in to Antigravity through the ``agy`` CLI.

The Antigravity ACP lane is keyless: ``agy`` authenticates itself and the
gateway never sees the token.  On a desktop Linux host the token lives in the
keyring as one entry for the whole installation (``service=gemini``,
``user=antigravity``), so every provider of this shim shares one Google
account there.  A headless host or container has no keyring; ``agy`` then
falls back to a token file under its ``--gemini-dir``.  The gateway gives each
lane a persistent ``--gemini-dir`` under its data directory, so both the admin
sign-in and the ACP agent use the same store, and a mounted data volume keeps
it across restarts and image upgrades.

This exchange is therefore **vendor-managed**: it keeps the lane keyless and
never mints or seeds a credential.  It drives ``agy acp --login`` with the
same ``--gemini-dir`` the transport will use, returns the Google URL that
command prints, writes the pasted code back, and reports the account the CLI
wrote to the keyring.  The token itself is never read into the gateway's
credential ring and never appears in a response.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from llm_rosetta.contracts.auth import (
    AuthContext,
    AuthExchangeError,
    BaseAuthExchange,
)

from llm_rosetta.contracts.cli_login import (
    CliLoginError,
    begin_cli_login,
    cancel_cli_login,
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


def _home(ctx: AuthContext) -> str:
    """The lane's persistent directory, as the gateway named it to the agent."""
    return _acp_env(ctx).get("LLM_ROSETTA_ACP_HOME", "")


def _declared_argv(ctx: AuthContext) -> list[str]:
    """The agent command the ACP transport will start, when the entry sets one.

    ``acp.argv`` is the current spelling; ``acp_argv`` is its older alias.
    Both name an install — another version is another path — while the profile
    stays in ``acp.home``.
    """
    config = ctx.config or {}
    block = config.get("acp")
    argv = block.get("argv") if isinstance(block, dict) else None
    if not isinstance(argv, (list, tuple)) or not argv:
        argv = config.get("acp_argv")
    if not isinstance(argv, (list, tuple)) or not argv:
        return []
    return [str(part) for part in argv]


#: Executable names the transport treats as the Antigravity CLI.  Kept in
#: sync with ``llm_rosetta_gateway.transport.acp_profile.is_agy``; the gateway
#: distribution is not a dependency of this package, so the literal cannot be
#: imported here.
AGY_NAMES = ("agy", "agy.real", "agy.exe")

#: The profile flags, with the same spellings as
#: ``llm_rosetta_gateway.transport.acp_profile._GEMINI_FLAGS``.
_GEMINI_FLAGS = ("--gemini-dir", "--gemini_dir")


def _is_agy(argv: list[str]) -> bool:
    return bool(argv) and Path(argv[0]).name in AGY_NAMES


def _gemini_dir(argv: list[str]) -> str | None:
    """The last non-empty ``--gemini-dir`` an agent command names, if any."""
    found: str | None = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        for name in _GEMINI_FLAGS:
            if arg == name:
                if index + 1 < len(argv) and argv[index + 1]:
                    found = argv[index + 1]
                index += 2
                break
            if arg.startswith(name + "="):
                value = arg.split("=", 1)[1]
                if value:
                    found = value
                index += 1
                break
        else:
            index += 1
    return found


def _without_gemini_dir(argv: list[str]) -> list[str]:
    """Drop the profile flags, so only the command's own tokens remain."""
    out: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        for name in _GEMINI_FLAGS:
            if arg == name:
                index += 2
                break
            if arg.startswith(name + "="):
                index += 1
                break
        else:
            out.append(arg)
            index += 1
    return out


def _gateway_owned_profile(ctx: AuthContext) -> bool:
    """Whether the agent will run in the profile ``acp.home`` names.

    The transport's three-state rule is mirrored here: an absent
    ``acp.harden`` follows the executable's name (``agy``), ``true`` forces
    the profile on a wrapper or a renamed binary, and ``false`` runs the
    command as written.  With no command in the entry the shim's default is
    ``agy``, so the home is owned.
    """
    block = (ctx.config or {}).get("acp")
    declared = block.get("harden") if isinstance(block, dict) else None
    if declared is not None:
        return declared is True
    argv = _declared_argv(ctx)
    if not argv:
        return True
    return _is_agy(argv)


def _login_argv(ctx: AuthContext) -> list[str]:
    """``agy acp --login`` in the same profile the ACP transport starts.

    The configured command is kept up to its ``acp`` subcommand, so an install
    started through a wrapper (``npx``, a version shim) signs in through that
    same wrapper; flags the entry adds after ``acp`` and a profile flag are
    left out.  A command that already names ``--gemini-dir`` is signed in
    there: the transport keeps that directory as the profile, so the sign-in
    must write the same one even on a core that predates the shared home
    variable.  Otherwise the gateway-owned home is used when the command is
    owned, and the CLI's own default when it is not.
    """
    declared = _declared_argv(ctx)
    stripped = _without_gemini_dir(declared)
    if "acp" in stripped:
        # The last ``acp`` token is the subcommand; an earlier one can be a
        # flag value (``--label acp``).
        end = len(stripped) - 1 - stripped[::-1].index("acp")
        prefix = stripped[: end + 1]
    elif declared and _is_agy(declared):
        prefix = [declared[0], "acp"]
    elif stripped:
        raise AuthExchangeError(
            "cannot derive a sign-in command from this acp.argv: it names no "
            "`acp` subcommand and its executable is not `agy`. Set acp.argv "
            "to ['<agy>', 'acp'], or run the vendor CLI's own sign-in."
        )
    else:
        prefix = [_executable(ctx), "acp"]
    argv = [*prefix, "--login"]
    home = _gemini_dir(declared)
    if home is None and _gateway_owned_profile(ctx):
        home = _home(ctx)
    if home:
        argv += ["--gemini-dir", home]
    return argv


#: A non-secret note that the vendor CLI completed a sign-in.  A headless host
#: has no keyring, so the CLI cannot be asked; this marker lives in the same
#: persistent home and tells the panel not to offer setup after a restart.
#: It holds no token, only the time the CLI reported success.
LOGIN_MARKER = ".llm-rosetta-login.json"


def _home_dir(ctx: AuthContext) -> Path | None:
    """The lane's persistent directory, or the record directory on old cores."""
    root = _home(ctx) or ctx.state_dir
    return Path(root) if root else None


def _read_marker(ctx: AuthContext) -> dict[str, Any] | None:
    """The sign-in marker, if this lane has one and it is readable."""
    root = _home_dir(ctx)
    if root is None:
        return None
    try:
        data = json.loads((root / LOGIN_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_marker(ctx: AuthContext) -> None:
    """Record that the CLI reported success, without recording any token."""
    root = _home_dir(ctx)
    if root is None:
        return
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:  # pragma: no cover - a filesystem that refuses chmod
        pass
    path = root / LOGIN_MARKER
    temp = root / f".{LOGIN_MARKER}.tmp"
    temp.write_text(
        json.dumps({"connected": True, "at": time.time()}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def _clear_marker(ctx: AuthContext) -> bool:
    """Remove the sign-in marker, returning whether one was there."""
    root = _home_dir(ctx)
    if root is None:
        return False
    try:
        (root / LOGIN_MARKER).unlink()
    except FileNotFoundError:
        return False
    except OSError:
        return False
    return True


def _executable(ctx: AuthContext) -> str:
    """The ``agy`` binary the provider starts, or a clear error."""
    argv = _declared_argv(ctx)
    if argv and argv[0]:
        return argv[0]
    found = shutil.which("agy")
    if found:
        return found
    raise AuthExchangeError(
        "the `agy` CLI is not on the gateway's PATH, so the admin sign-in "
        "cannot drive it; install Antigravity CLI or set this provider's "
        "acp.argv (or acp_argv) to its path"
    )


def _keyring_available() -> bool:
    return shutil.which("secret-tool") is not None


def _session_env() -> dict[str, str]:
    """The environment a desktop keyring lookup needs.

    ``secret-tool`` speaks to the session bus, so it needs
    ``DBUS_SESSION_BUS_ADDRESS`` and ``XDG_RUNTIME_DIR``.  A login session sets
    both, but a gateway started by a service manager or a bare shell may have
    neither even though the bus exists.  ``agy`` finds the same store on its
    own; only the shim's lookup needs the repair, so fill in the per-user path
    when the socket is there and leave a host without one untouched.
    """
    env = dict(os.environ)
    runtime = env.get("XDG_RUNTIME_DIR", "")
    if not runtime:
        candidate = f"/run/user/{os.getuid()}"
        if os.path.isdir(candidate):
            runtime = candidate
            env["XDG_RUNTIME_DIR"] = candidate
    if runtime and not env.get("DBUS_SESSION_BUS_ADDRESS"):
        bus = os.path.join(runtime, "bus")
        if os.path.exists(bus):
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"
    return env


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
        env=_session_env(),
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
        """Whether this host has no account it can see.

        A keyring host answers from the keyring.  A headless host answers from
        the marker the last successful sign-in wrote in the lane's persistent
        home: the CLI's own token is not readable there, but the gateway can
        still tell a restarted deployment with a finished sign-in from one
        that never signed in.
        """
        if not _keyring_available():
            return _read_marker(ctx) is None
        return _read_account() is None

    def setup_state_is_authoritative(self, ctx: AuthContext) -> bool:
        """Return ``False``: a missing account is not proof of a sign-out.

        The CLI keeps its token in a store the gateway may not be able to
        read: a keyring lookup can fail because the collection is locked, and
        a headless terminal sign-in leaves no marker.  Both look exactly like
        "nobody signed in".  The readiness probe must ask the agent, which is
        the only authority on its own session.
        """
        return False

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
        if data:
            return _summary(data)
        if _keyring_available():
            return None
        marker = _read_marker(ctx)
        return _summary(marker) if marker else None

    def begin_login(self, ctx: AuthContext) -> dict[str, Any]:
        """Run ``agy acp --login`` in the lane's persistent profile."""
        try:
            return begin_cli_login(
                ctx.provider,
                _login_argv(ctx),
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
            # The CLI exited 0 and this host cannot read the keyring.  The CLI
            # is the authority on its own sign-in; the marker lets a later
            # render, including after a restart, know it finished.
            _write_marker(ctx)
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

    def revoke(self, ctx: AuthContext) -> bool:
        """Sign out locally, without claiming the Google grant was revoked.

        The CLI owns the upstream session.  This removes what the panel reads:
        the headless marker and, when a keyring is present, the entry ``agy``
        wrote.  ``False`` means the local record is gone but the Google grant
        may still be live upstream.
        """
        cancel_cli_login(ctx.provider)
        _clear_marker(ctx)
        if _keyring_available():
            run_capture(
                [
                    "secret-tool",
                    "clear",
                    "service",
                    KEYRING_SERVICE,
                    "username",
                    KEYRING_USER,
                ],
                env=_session_env(),
                timeout=10.0,
            )
        return False


EXCHANGE = AntigravityCliExchange()
