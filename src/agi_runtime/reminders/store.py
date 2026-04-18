from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class ReminderJob:
    id: str
    principal_id: str
    chat_id: str
    user_id: str
    message: str
    schedule_kind: str  # once | cron
    run_at: float | None = None
    cron_expr: str | None = None
    timezone: str = "UTC"
    enabled: bool = True
    running_at: float | None = None
    next_run_at: float | None = None
    last_run_at: float | None = None
    last_status: str = ""
    last_error: str = ""
    consecutive_errors: int = 0
    last_delivery_key: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


class ReminderStore:
    def __init__(self, path: str = "memory/reminders.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list_jobs(self, *, principal_id: str | None = None, include_disabled: bool = True) -> list[ReminderJob]:
        jobs = self._load()
        out = []
        for job in jobs:
            if principal_id and job.principal_id != principal_id:
                continue
            if not include_disabled and not job.enabled:
                continue
            out.append(job)
        return sorted(out, key=lambda j: (j.next_run_at or float("inf"), j.created_at))

    def get_job(self, job_id: str) -> ReminderJob | None:
        for job in self._load():
            if job.id == job_id:
                return job
        return None

    def create_job(
        self,
        *,
        principal_id: str,
        chat_id: str,
        user_id: str,
        message: str,
        schedule_kind: str,
        run_at: float | None,
        cron_expr: str | None,
        timezone: str,
        next_run_at: float | None,
    ) -> ReminderJob:
        now = time.time()
        job = ReminderJob(
            id=uuid.uuid4().hex[:12],
            principal_id=principal_id,
            chat_id=chat_id,
            user_id=user_id,
            message=message,
            schedule_kind=schedule_kind,
            run_at=run_at,
            cron_expr=cron_expr,
            timezone=timezone,
            next_run_at=next_run_at,
            created_at=now,
            updated_at=now,
        )
        jobs = self._load()
        jobs.append(job)
        self._save(jobs)
        return job

    def update_job(self, job_id: str, **changes: Any) -> ReminderJob | None:
        jobs = self._load()
        target = None
        for job in jobs:
            if job.id != job_id:
                continue
            target = job
            for key, value in changes.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = time.time()
            break
        if target is None:
            return None
        self._save(jobs)
        return target

    def remove_job(self, job_id: str) -> bool:
        jobs = self._load()
        kept = [j for j in jobs if j.id != job_id]
        if len(kept) == len(jobs):
            return False
        self._save(kept)
        return True

    def due_jobs(
        self,
        *,
        now_ts: float,
        stuck_seconds: float = 600.0,
        oneshot_grace_seconds: float = 300.0,
    ) -> list[ReminderJob]:
        jobs = self._load()
        due: list[ReminderJob] = []
        changed = False
        for job in jobs:
            if not job.enabled:
                continue
            if job.running_at and now_ts - job.running_at < stuck_seconds:
                continue
            if job.running_at and now_ts - job.running_at >= stuck_seconds:
                job.running_at = None
                job.last_status = "stuck_recovered"
                changed = True
            if job.next_run_at is None:
                continue
            if job.schedule_kind == "once" and now_ts - job.next_run_at > oneshot_grace_seconds:
                # Too stale; disable to avoid surprise reminders after long downtime.
                job.enabled = False
                job.last_status = "missed"
                changed = True
                continue
            if job.next_run_at <= now_ts:
                due.append(job)

        if changed:
            self._save(jobs)
        return sorted(due, key=lambda j: j.next_run_at or now_ts)

    def mark_running(self, job_id: str, *, now_ts: float, delivery_key: str) -> ReminderJob | None:
        return self.update_job(job_id, running_at=now_ts, last_delivery_key=delivery_key, last_status="running")

    def mark_succeeded(self, job_id: str, *, now_ts: float, next_run_at: float | None) -> ReminderJob | None:
        changes = {
            "running_at": None,
            "last_run_at": now_ts,
            "last_status": "ok",
            "last_error": "",
            "consecutive_errors": 0,
            "next_run_at": next_run_at,
        }
        if next_run_at is None:
            changes["enabled"] = False
        return self.update_job(job_id, **changes)

    def mark_failed(self, job_id: str, *, now_ts: float, error: str, retry_at: float) -> ReminderJob | None:
        job = self.get_job(job_id)
        current_errors = int(job.consecutive_errors) if job else 0
        return self.update_job(
            job_id,
            running_at=None,
            last_run_at=now_ts,
            last_status="error",
            last_error=(error or "")[:500],
            consecutive_errors=current_errors + 1,
            next_run_at=retry_at,
        )

    def _load(self) -> list[ReminderJob]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(raw, dict):
            return []
        rows = raw.get("jobs", [])
        if not isinstance(rows, list):
            return []
        out: list[ReminderJob] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                out.append(ReminderJob(**row))
            except TypeError:
                continue
        return out

    def _save(self, jobs: list[ReminderJob]) -> None:
        payload = {
            "version": 1,
            "updated_at": time.time(),
            "jobs": [asdict(j) for j in jobs],
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)


def principal_to_telegram(principal_id: str) -> tuple[str, str]:
    """Extract Telegram chat_id and user_id from principal id."""
    pid = (principal_id or "").strip()
    # telegram:group:{chat_id}:user:{user_id}
    parts = pid.split(":")
    if len(parts) >= 5 and parts[0] == "telegram" and parts[1] == "group":
        return parts[2], parts[4]
    # telegram:dm:{user_id}
    if len(parts) >= 3 and parts[0] == "telegram" and parts[1] == "dm":
        uid = parts[2]
        return uid, uid
    return "", ""

