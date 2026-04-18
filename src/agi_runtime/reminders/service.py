from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from agi_runtime.reminders.parse import parse_schedule_input
from agi_runtime.reminders.schedule import ScheduleRequest, next_run_at
from agi_runtime.reminders.store import ReminderStore, principal_to_telegram


@dataclass
class ReminderCreateResult:
    ok: bool
    message: str
    job_id: str = ""
    next_run_at: float | None = None


class ReminderService:
    def __init__(self, store: ReminderStore | None = None):
        self.store = store or ReminderStore()

    def create(self, *, principal_id: str, message: str, schedule: str, timezone: str = "UTC") -> ReminderCreateResult:
        message = (message or "").strip()
        if not message:
            return ReminderCreateResult(ok=False, message="Reminder message is required.")

        chat_id, user_id = principal_to_telegram(principal_id)
        if not chat_id:
            return ReminderCreateResult(ok=False, message="Reminders currently support Telegram principals only.")

        try:
            parsed = parse_schedule_input(schedule, timezone=timezone)
        except Exception as exc:
            return ReminderCreateResult(ok=False, message=f"Invalid schedule: {exc}")

        req = ScheduleRequest(
            kind=parsed.kind,
            run_at=parsed.run_at,
            cron_expr=parsed.cron_expr,
            timezone=parsed.timezone or timezone,
        )
        now_ts = time.time()
        nr = next_run_at(req, now_ts=now_ts)
        if nr is None:
            return ReminderCreateResult(ok=False, message="Schedule does not produce a future run time.")

        job = self.store.create_job(
            principal_id=principal_id,
            chat_id=chat_id,
            user_id=user_id,
            message=message,
            schedule_kind=parsed.kind,
            run_at=parsed.run_at,
            cron_expr=parsed.cron_expr,
            timezone=parsed.timezone or timezone,
            next_run_at=nr,
        )
        return ReminderCreateResult(
            ok=True,
            message=f"Created reminder `{job.id}` for {self._fmt_ts(nr, job.timezone)}.",
            job_id=job.id,
            next_run_at=nr,
        )

    def list_for_principal(self, principal_id: str) -> str:
        jobs = self.store.list_jobs(principal_id=principal_id, include_disabled=True)
        if not jobs:
            return "No reminders yet."
        lines = []
        for j in jobs:
            status = "enabled" if j.enabled else "disabled"
            sched = f"cron:{j.cron_expr}" if j.schedule_kind == "cron" else self._fmt_ts(j.run_at, j.timezone)
            nxt = self._fmt_ts(j.next_run_at, j.timezone) if j.next_run_at else "-"
            lines.append(f"- {j.id} | {status} | next: {nxt} | {sched} | {j.message}")
        return "\n".join(lines)

    def cancel(self, principal_id: str, job_id: str) -> str:
        job = self.store.get_job(job_id)
        if not job or job.principal_id != principal_id:
            return f"Reminder `{job_id}` not found."
        self.store.remove_job(job_id)
        return f"Cancelled reminder `{job_id}`."

    def pause(self, principal_id: str, job_id: str) -> str:
        job = self.store.get_job(job_id)
        if not job or job.principal_id != principal_id:
            return f"Reminder `{job_id}` not found."
        self.store.update_job(job_id, enabled=False, last_status="paused")
        return f"Paused reminder `{job_id}`."

    def resume(self, principal_id: str, job_id: str) -> str:
        job = self.store.get_job(job_id)
        if not job or job.principal_id != principal_id:
            return f"Reminder `{job_id}` not found."
        req = ScheduleRequest(
            kind=job.schedule_kind,
            run_at=job.run_at,
            cron_expr=job.cron_expr,
            timezone=job.timezone,
        )
        nr = next_run_at(req, now_ts=time.time())
        self.store.update_job(job_id, enabled=True, next_run_at=nr, last_status="resumed")
        return f"Resumed reminder `{job_id}`."

    def run_now(self, principal_id: str, job_id: str) -> str:
        job = self.store.get_job(job_id)
        if not job or job.principal_id != principal_id:
            return f"Reminder `{job_id}` not found."
        self.store.update_job(job_id, next_run_at=time.time(), enabled=True)
        return f"Reminder `{job_id}` scheduled to run now."

    @staticmethod
    def _fmt_ts(ts: float | None, tz_name: str) -> str:
        if ts is None:
            return "-"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = dt_timezone.utc
        return datetime.fromtimestamp(ts, tz=tz).strftime("%Y-%m-%d %H:%M:%S %Z")

