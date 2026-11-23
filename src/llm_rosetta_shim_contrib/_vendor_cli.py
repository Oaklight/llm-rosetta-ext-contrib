"""Drive a vendor CLI's interactive sign-in from the admin panel.

Both ACP lanes keep their credential in the vendor CLI's own store: Claude
Code writes ``$CLAUDE_CONFIG_DIR`` (``~/.claude`` when unset), and the
Antigravity CLI writes a Google account token to the desktop keyring, or to a
file under its ``--gemini-dir`` when no keyring is available.  The gateway
gives each lane a persistent directory under its data directory and passes it
to the CLI here, so an admin sign-in lands in the same profile the agent will
use and survives a restart or image upgrade.  The gateway never sees that
token, so the ``auth.py`` exchange for such a lane cannot mint one.  What it
can do is run the vendor's own sign-in command, show the operator the URL
that command prints, and feed the pasted code back to the waiting process.

That is what this module provides.  It is deliberately small and
standard-library only: the shim layer loads before the gateway and has no
dependencies.  One pending sign-in per key (the gateway provider name) is
kept; starting again replaces the old process, and an abandoned flow is
terminated when it expires or when the gateway exits.

The flow is the same for every CLI:

1. ``begin_cli_login`` spawns the command with pipes and reads its stdout on
   a worker thread until it prints an authorization URL.
2. The process is left waiting on stdin.  The admin panel opens the URL and
   asks the operator for the code (or the full callback URL) the vendor shows.
3. ``complete_cli_login`` writes that value to stdin, waits for the process to
   exit, and then lets the caller verify the result.

Nothing here parses or stores a credential.  A failure message is built from
the process's own output, with the pasted value redacted.
"""

from __future__ import annotations

import atexit
import os
import re
import subprocess
import threading
import time
from collections import deque
from typing import Any

#: How long a pending sign-in may sit unfinished before its process is killed.
PENDING_TTL = 600.0

#: How long the CLI gets to print its authorization URL.
URL_TIMEOUT = 30.0

#: How long the CLI gets to finish after the pasted value is written.
COMPLETE_TIMEOUT = 120.0

#: What the admin panel calls the pasted input.
PASTE_LABEL = "Paste the code (or the callback URL) the vendor page shows"
PASTE_PLACEHOLDER = "the code shown after signing in"

_URL_RE = re.compile(r"https://[^\s\x1b\x07\"'<>]+")
#: A URL is the sign-in URL when it looks like one, not merely the first link
#: a CLI prints (a header or a documentation link is common).
_LOGIN_URL_HINTS = ("oauth", "authorize", "accounts.google.com", "claude.com")

#: Token shapes a verbose CLI may print even though the gateway asked for a
#: URL.  The pasted code is redacted exactly; these catch the vendor's own
#: echoes.  A false positive on a diagnostic word is harmless.
_TOKEN_RES = (
    re.compile(r"\bya29\.[A-Za-z0-9._\-]+"),
    re.compile(r"\b1//[A-Za-z0-9._\-]+"),
    re.compile(r"\bsk-[A-Za-z0-9._\-]{8,}"),
    re.compile(r"\bAIza[0-9A-Za-z._\-]{20,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=\-]{8,}"),
)

_LOCK = threading.Lock()
_PENDING: dict[str, "_Pending"] = {}


class CliLoginError(Exception):
    """The CLI could not start, refused the code, or did not finish."""


class _Pending:
    def __init__(
        self,
        process: subprocess.Popen[str],
        *,
        deadline: float,
    ) -> None:
        self.process = process
        self.deadline = deadline
        self.url = ""
        self.url_event = threading.Event()
        self.first_url = ""
        self.lines: deque[str] = deque(maxlen=200)
        self.timer: threading.Timer | None = None
        self.reader: threading.Thread | None = None

    def tail(self) -> str:
        text = "\n".join(self.lines).strip()
        return text[-1500:] if text else "(no output)"


def run_capture(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> tuple[int, str, str] | None:
    """Run a status command and return ``(code, stdout, stderr)``.

    ``None`` means the command could not be started (a missing binary, a
    permission error).  A caller treats that as "status unavailable", not as
    "signed in" or "signed out".
    """
    try:
        proc = subprocess.run(
            argv,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.returncode, proc.stdout, proc.stderr


def begin_cli_login(
    key: str,
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    ttl: float = PENDING_TTL,
    url_timeout: float = URL_TIMEOUT,
    paste_label: str = PASTE_LABEL,
    paste_placeholder: str = PASTE_PLACEHOLDER,
) -> dict[str, Any]:
    """Start one sign-in and return its authorization URL.

    Raises:
        CliLoginError: The command could not be started, exited before printing
            a URL, or printed none in time.
    """
    cancel_cli_login(key)
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
    except OSError as exc:
        raise CliLoginError(f"the sign-in command could not start: {exc}") from exc
    pending = _Pending(process, deadline=time.time() + ttl)
    reader = threading.Thread(
        target=_read_output, args=(pending,), name=f"vendor-login-{key}", daemon=True
    )
    pending.reader = reader
    reader.start()
    _wait_for_url(pending, url_timeout)
    url = pending.url or pending.first_url
    if not url:
        output = pending.tail()
        _terminate(pending)
        raise CliLoginError(
            f"the sign-in command printed no authorization URL; it said: {output}"
        )
    with _LOCK:
        _PENDING[key] = pending
    timer = threading.Timer(ttl, _expire, args=(key, pending))
    timer.daemon = True
    timer.start()
    pending.timer = timer
    return {
        "authorization_url": url,
        "expires_at": pending.deadline,
        "paste_label": paste_label,
        "paste_placeholder": paste_placeholder,
    }


def complete_cli_login(
    key: str,
    pasted: str,
    *,
    timeout: float = COMPLETE_TIMEOUT,
) -> None:
    """Write the operator's code to the waiting CLI and wait for it to exit.

    Raises:
        CliLoginError: No sign-in is pending, the process refused the value, or
            it did not finish in time.
    """
    value = _first_line(pasted)
    if not value:
        raise CliLoginError("a code or callback URL is required")
    with _LOCK:
        pending = _PENDING.pop(key, None)
    if pending is None:
        raise CliLoginError("no sign-in is pending; start again")
    if pending.timer is not None:
        pending.timer.cancel()
    if time.time() >= pending.deadline:
        _terminate(pending)
        raise CliLoginError("the sign-in expired; start again")
    process = pending.process
    try:
        assert process.stdin is not None
        process.stdin.write(value + "\n")
        process.stdin.flush()
    except (BrokenPipeError, OSError) as exc:
        output = pending.tail()
        _terminate(pending)
        raise CliLoginError(
            f"the sign-in command had already exited: {exc}; it said: {output}"
        ) from exc
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate(pending)
        raise CliLoginError(
            "the sign-in command did not finish after the code was entered"
        ) from exc
    _drain_reader(pending)
    output = pending.tail()
    if code != 0:
        raise CliLoginError(
            f"the sign-in command exited with {code}; it said: {_redact(output, value)}"
        )
    return None


def cancel_cli_login(key: str) -> None:
    """Stop a pending sign-in for *key*, if there is one."""
    with _LOCK:
        pending = _PENDING.pop(key, None)
    if pending is not None:
        if pending.timer is not None:
            pending.timer.cancel()
        _terminate(pending)


def _read_output(pending: _Pending) -> None:
    process = pending.process
    assert process.stdout is not None
    for line in process.stdout:
        pending.lines.append(line.rstrip("\n"))
        match = _URL_RE.search(line)
        if not match or pending.url:
            continue
        url = _clean_url(match.group(0))
        if not pending.first_url:
            pending.first_url = url
        if any(hint in url for hint in _LOGIN_URL_HINTS):
            pending.url = url
            pending.url_event.set()


def _wait_for_url(pending: _Pending, timeout: float) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pending.url:
            return
        if pending.process.poll() is not None:
            _drain_reader(pending)
            return
        time.sleep(0.05)


def _drain_reader(pending: _Pending) -> None:
    """Wait for the reader to consume what the process wrote before it exited.

    A short-lived failure mode (a bad flag, a missing key, a CLI that refuses
    to start) is the common case here.  Without this join the caller can report
    ``(no output)`` while the explanation sits unread in the pipe.
    """
    if pending.reader is not None:
        pending.reader.join(timeout=1.0)


def _clean_url(raw: str) -> str:
    return raw.rstrip(".,;:)\"'").strip()


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        value = line.strip()
        if value:
            return value
    return ""


def _redact(text: str, value: str) -> str:
    if value:
        text = text.replace(value, "<redacted>")
    for pattern in _TOKEN_RES:
        text = pattern.sub("<redacted>", text)
    return text


def _terminate(pending: _Pending) -> None:
    process = pending.process
    try:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
    except OSError:
        pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:  # pragma: no cover - unkillable
                pass


def _expire(key: str, pending: _Pending) -> None:
    with _LOCK:
        if _PENDING.get(key) is not pending:
            return
        _PENDING.pop(key, None)
    _terminate(pending)


def _cancel_all() -> None:
    with _LOCK:
        pending = list(_PENDING.values())
        _PENDING.clear()
    for item in pending:
        if item.timer is not None:
            item.timer.cancel()
        _terminate(item)


atexit.register(_cancel_all)


def subprocess_env(overrides: dict[str, str] | None) -> dict[str, str]:
    """The CLI's environment: the gateway's own plus the provider's switches.

    Mirrors the ACP transport's spawn rule, so the CLI signs in to the same
    profile the agent will use.
    """
    env = dict(os.environ)
    if overrides:
        env.update({str(k): str(v) for k, v in overrides.items()})
    return env
