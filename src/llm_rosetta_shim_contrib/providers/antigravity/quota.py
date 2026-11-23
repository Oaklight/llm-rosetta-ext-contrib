"""Antigravity quota probe — the plan's windows, read by the vendor's CLI.

The ACP surface says nothing about the account: an ``agy`` turn sends only
token counts, so the gateway cannot learn the plan's allowance from it.  The
CLI itself can print it, though, and the shim declares that command under
``quota.local``:

    agy -p "/usage" --output-format json

The command keeps the lane's profile through ``ANTIGRAVITY_APP_DATA_DIR``, so
the reading belongs to the same Google account the lane signs in with.  Its
reply names groups (Gemini models, Claude and GPT models), and each group has
a five-hour and a weekly bucket; every bucket reports ``remaining_fraction``
and ``reset_time``.  This module turns those buckets into windows.

Module scope deliberately imports only the standard library: shims load before
the gateway package, so the contract types are imported inside the methods.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from llm_rosetta.contracts.quota import QuotaWindow

#: The vendor's window key, its display name, and its length.
_WINDOWS = {
    "5h": ("5 hours", 5 * 3600),
    "weekly": ("7 days", 7 * 24 * 3600),
}

#: The wrapper around the command's payload.
_COMMAND_DATA = "command"


class AntigravityUsageProbe:
    """The allowance of the Google account ``agy`` is signed in to."""

    id = "antigravity_usage"
    default_url: str | None = None

    def match(self, base_url: str) -> str | None:
        """Recognise an Antigravity lane; it has no HTTP usage endpoint."""
        return ""

    def headers(self, key: str) -> dict[str, str]:
        """The local command sends no request, so it carries no headers."""
        return {}

    def parse(self, body: Any) -> tuple[str | None, list[QuotaWindow]]:
        """Refuse an HTTP read: this vendor is read only through its CLI."""
        from llm_rosetta.contracts.quota import QuotaProbeError

        raise QuotaProbeError(
            "Antigravity's allowance is read by its own CLI, not an HTTP endpoint"
        )

    def parse_local(self, body: Any) -> tuple[str | None, list[QuotaWindow]]:
        """Decode the JSON printed by ``agy -p "/usage" --output-format json``.

        Args:
            body: The decoded stdout.  The command wraps its payload in
                ``{"status": ..., "command": {"data": {"groups": [...]}}}``;
                a bare ``{"groups": [...]}`` is accepted too.

        Returns:
            ``(None, windows)``, one window per group bucket, named after the
            group ("Gemini Models — 5 hours").

        Raises:
            QuotaProbeError: The command failed, or its payload named no
                bucket with a remaining share.
        """
        from llm_rosetta.contracts.quota import QuotaProbeError, QuotaWindow
        from llm_rosetta.contracts.quota import parse_iso

        payload = body if isinstance(body, dict) else {}
        status = payload.get("status")
        if isinstance(status, str) and status and status.upper() != "SUCCESS":
            raise QuotaProbeError(_refusal(payload))
        data = payload.get(_COMMAND_DATA)
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]
        groups = data.get("groups") if isinstance(data, dict) else None
        if not isinstance(groups, list):
            groups = payload.get("groups")
        if not isinstance(groups, list):
            raise QuotaProbeError(
                f"the usage command printed no groups (got {_brief(payload)})"
            )

        windows: list[QuotaWindow] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            group_name = str(group.get("name") or "").strip()
            buckets = group.get("buckets")
            if not isinstance(buckets, list):
                continue
            for bucket in buckets:
                window = _window_of(bucket, group_name, QuotaWindow, parse_iso)
                if window is not None:
                    windows.append(window)
        if not windows:
            raise QuotaProbeError(
                f"the usage command named no allowance window (got {_brief(payload)})"
            )
        return None, windows

    def describe_error(self, status_code: int, body: Any) -> str:
        """Name the status of an HTTP read, which this probe never makes."""
        return f"the usage command failed (HTTP {status_code})"

    def inband(self, status_code: int, body: Any) -> None:
        """This lane exposes no in-band quota signal."""
        return None


def _window_of(bucket: Any, group: str, window_type: Any, parse_iso: Any) -> Any:
    """One group bucket as a ``QuotaWindow``, or ``None`` if it carries none."""
    if not isinstance(bucket, dict) or bucket.get("disabled"):
        return None
    remaining = bucket.get("remaining_fraction")
    if isinstance(remaining, bool) or not isinstance(remaining, (int, float)):
        return None
    key = str(bucket.get("window") or "")
    display, span = _WINDOWS.get(key, (key, None))
    if not display:
        return None
    share = max(0.0, min(1.0, float(remaining)))
    name = f"{group} — {display}" if group else display
    return window_type(
        name=name,
        used_percent=round((1.0 - share) * 100.0, 2),
        span_seconds=span,
        resets_at=parse_iso(bucket.get("reset_time")),
        status="ok",
    )


def _refusal(payload: dict[str, Any]) -> str:
    """The CLI's own words when it reports a failed command."""
    for key in ("response", "error", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return f"the usage command failed: {value.strip()[:300]}"
    return f"the usage command failed (status {payload.get('status')!r})"


def _brief(payload: Any) -> str:
    """A short, secret-free view of a payload for an error message."""
    text = repr(payload)
    return text[:300]


PROBES = (AntigravityUsageProbe(),)
