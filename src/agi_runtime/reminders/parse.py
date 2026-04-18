from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo


_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhdw])\s*$", re.IGNORECASE)
_IN_RE = re.compile(r"^\s*in\s+(\d+)\s*([smhdw])\s*$", re.IGNORECASE)
_TODAY_TOMORROW_RE = re.compile(
    r"^\s*(today|tomorrow)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$",
    re.IGNORECASE,
)


@dataclass
class ParsedSchedule:
    kind: str  # once | cron
    run_at: float | None = None
    cron_expr: str | None = None
    timezone: str | None = None
    display: str = ""


def parse_schedule_input(text: str, *, timezone: str = "UTC", now_ts: float | None = None) -> ParsedSchedule:
    text = (text or "").strip()
    if not text:
        raise ValueError("Schedule is required.")

    now_ts = time.time() if now_ts is None else now_ts
    tz = _safe_zone(timezone)

    if text.lower().startswith("cron:"):
        expr = text.split(":", 1)[1].strip()
        _validate_cron_expr(expr, tz)
        return ParsedSchedule(kind="cron", cron_expr=expr, timezone=timezone, display=f"cron:{expr}")

    # Pure 5-field cron support
    parts = text.split()
    if len(parts) == 5:
        expr = " ".join(parts)
        _validate_cron_expr(expr, tz)
        return ParsedSchedule(kind="cron", cron_expr=expr, timezone=timezone, display=f"cron:{expr}")

    run_at = _parse_natural_once(text, tz=tz, now_ts=now_ts)
    return ParsedSchedule(kind="once", run_at=run_at, timezone=timezone, display=text)


def _parse_natural_once(text: str, *, tz: ZoneInfo, now_ts: float) -> float:
    m = _IN_RE.match(text)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        return now_ts + _seconds_for_unit(amount, unit)

    m = _DURATION_RE.match(text)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        return now_ts + _seconds_for_unit(amount, unit)

    m = _TODAY_TOMORROW_RE.match(text)
    if m:
        day_word = m.group(1).lower()
        hh = int(m.group(2))
        mm = int(m.group(3) or "0")
        ampm = (m.group(4) or "").lower()
        if ampm:
            if hh < 1 or hh > 12:
                raise ValueError("Invalid hour in 12h time format.")
            if ampm == "pm" and hh != 12:
                hh += 12
            if ampm == "am" and hh == 12:
                hh = 0
        elif hh > 23:
            raise ValueError("Hour must be 0-23 for 24h format.")
        if mm > 59:
            raise ValueError("Minute must be 0-59.")

        now = datetime.fromtimestamp(now_ts, tz=tz)
        target_date = now.date()
        if day_word == "tomorrow":
            target_date = target_date + timedelta(days=1)
        dt = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hh,
            mm,
            tzinfo=tz,
        )
        if day_word == "today" and dt.timestamp() <= now_ts:
            raise ValueError("Specified time for today is already in the past.")
        return dt.timestamp()

    # ISO-ish fallback
    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        ts = dt.timestamp()
        if ts <= now_ts:
            raise ValueError("Reminder time must be in the future.")
        return ts
    except Exception as exc:
        raise ValueError(
            "Unsupported schedule format. Use 'in 30m', 'tomorrow 9am', "
            "'YYYY-MM-DD HH:MM', or 'cron:<expr>'."
        ) from exc


def _safe_zone(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        return dt_timezone.utc


def _seconds_for_unit(amount: int, unit: str) -> int:
    if amount <= 0:
        raise ValueError("Duration must be greater than 0.")
    if unit == "s":
        return amount
    if unit == "m":
        return amount * 60
    if unit == "h":
        return amount * 3600
    if unit == "d":
        return amount * 86400
    if unit == "w":
        return amount * 7 * 86400
    raise ValueError(f"Unsupported duration unit: {unit}")


def _validate_cron_expr(expr: str, tz: ZoneInfo) -> None:
    try:
        from croniter import croniter
    except Exception as exc:
        raise ValueError("croniter dependency is required for cron expressions.") from exc

    try:
        croniter(expr, datetime.now(tz))
    except Exception as exc:
        raise ValueError(f"Invalid cron expression: {expr}") from exc

