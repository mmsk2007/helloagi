from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo


@dataclass
class ScheduleRequest:
    kind: str  # once | cron
    run_at: float | None = None
    cron_expr: str | None = None
    timezone: str = "UTC"


def next_run_at(req: ScheduleRequest, *, now_ts: float) -> float | None:
    if req.kind == "once":
        return req.run_at if (req.run_at and req.run_at > now_ts) else None

    if req.kind == "cron":
        if not req.cron_expr:
            return None
        try:
            from croniter import croniter
        except Exception:
            return None
        tz = _safe_zone(req.timezone)
        base = datetime.fromtimestamp(now_ts, tz=tz)
        return float(croniter(req.cron_expr, base).get_next(float))

    return None


def retry_backoff_seconds(consecutive_errors: int) -> float:
    # 30s, 60s, 120s, 240s ... capped at 1 hour
    consecutive_errors = max(0, consecutive_errors)
    return min(3600.0, 30.0 * (2 ** consecutive_errors))


def _safe_zone(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        return dt_timezone.utc

