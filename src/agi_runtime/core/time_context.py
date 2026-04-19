"""Time context for the agent.

Provides a single source of truth for "what time is it, for this principal?".
Resolves effective timezone (principal override → runtime setting → host local),
renders a compact <time-context> block for the system prompt, and provides
a short envelope prefix for inbound channel messages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def _try_zoneinfo(name: str):
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    except ImportError:
        return None
    try:
        return ZoneInfo(name)
    except Exception:
        return None


def resolve_timezone(
    principal_tz: Optional[str] = None,
    settings_tz: Optional[str] = None,
):
    """Return (tzinfo, label). label is the IANA name if known, else the UTC offset.

    Resolution order: principal override → runtime setting → host local.
    """
    for candidate in (principal_tz, settings_tz):
        if candidate:
            tz = _try_zoneinfo(candidate)
            if tz is not None:
                return tz, candidate

    host = datetime.now().astimezone().tzinfo
    offset = datetime.now(host).strftime("%z") or "+0000"
    pretty = f"UTC{offset[:3]}:{offset[3:]}" if offset else "UTC"
    return host, pretty


def build_time_context_block(
    principal_tz: Optional[str] = None,
    settings_tz: Optional[str] = None,
) -> str:
    """Return a compact block for injection into the agent system prompt."""
    tz, label = resolve_timezone(principal_tz, settings_tz)
    local = datetime.now(tz)
    utc = datetime.now(timezone.utc)
    offset = local.strftime("%z")
    offset_pretty = f"{offset[:3]}:{offset[3:]}" if offset else "+00:00"
    return (
        f"Current date: {local.strftime('%A, %Y-%m-%d')}\n"
        f"Local time: {local.strftime('%H:%M')} ({offset_pretty}, {label})\n"
        f"UTC: {utc.strftime('%Y-%m-%dT%H:%MZ')}"
    )


def envelope_prefix(
    channel: str,
    principal_tz: Optional[str] = None,
    settings_tz: Optional[str] = None,
) -> str:
    """Short timestamp prefix for inbound channel messages.

    Example: ``[Telegram 2026-04-19 14:22 Asia/Riyadh]``
    """
    tz, label = resolve_timezone(principal_tz, settings_tz)
    local = datetime.now(tz)
    return f"[{channel} {local.strftime('%Y-%m-%d %H:%M')} {label}]"
