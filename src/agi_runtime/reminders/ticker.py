from __future__ import annotations

import asyncio
import os
import time
from typing import Awaitable, Callable

from agi_runtime.reminders.run_log import ReminderRunLog
from agi_runtime.reminders.schedule import ScheduleRequest, next_run_at, retry_backoff_seconds
from agi_runtime.reminders.store import ReminderJob, ReminderStore


DispatchFn = Callable[[ReminderJob], Awaitable[None]]


class ReminderTicker:
    def __init__(
        self,
        *,
        store: ReminderStore | None = None,
        run_log: ReminderRunLog | None = None,
        dispatch: DispatchFn,
        tick_seconds: float | None = None,
        stuck_seconds: float | None = None,
        oneshot_grace_seconds: float | None = None,
    ):
        self.store = store or ReminderStore()
        self.run_log = run_log or ReminderRunLog()
        self.dispatch = dispatch
        self.tick_seconds = tick_seconds or float(os.environ.get("HELLOAGI_REMINDER_TICK_SECONDS", "5"))
        self.stuck_seconds = stuck_seconds or float(os.environ.get("HELLOAGI_REMINDER_STUCK_SECONDS", "600"))
        self.oneshot_grace_seconds = oneshot_grace_seconds or float(
            os.environ.get("HELLOAGI_REMINDER_ONESHOT_GRACE_SECONDS", "300")
        )
        self._task: asyncio.Task | None = None
        # Created lazily in start() so constructing ReminderTicker without a
        # running loop (e.g. sync tests) does not call deprecated get_event_loop().
        self._stop: asyncio.Event | None = None

    async def start(self) -> None:
        if self._stop is None:
            self._stop = asyncio.Event()
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass

    async def run_once(self) -> int:
        now = time.time()
        due = self.store.due_jobs(
            now_ts=now,
            stuck_seconds=self.stuck_seconds,
            oneshot_grace_seconds=self.oneshot_grace_seconds,
        )
        count = 0
        for job in due:
            delivery_key = f"{job.id}:{int(job.next_run_at or now)}"
            if job.last_status == "ok" and job.last_delivery_key == delivery_key:
                continue
            self.store.mark_running(job.id, now_ts=now, delivery_key=delivery_key)
            try:
                await self.dispatch(job)
                count += 1
                self.run_log.append(job.id, "delivered", detail=job.message)
                req = ScheduleRequest(
                    kind=job.schedule_kind,
                    run_at=job.run_at,
                    cron_expr=job.cron_expr,
                    timezone=job.timezone,
                )
                nra = next_run_at(req, now_ts=now) if job.schedule_kind == "cron" else None
                self.store.mark_succeeded(job.id, now_ts=now, next_run_at=nra)
            except Exception as exc:
                self.run_log.append(job.id, "error", detail=str(exc))
                backoff = retry_backoff_seconds(job.consecutive_errors + 1)
                self.store.mark_failed(job.id, now_ts=now, error=str(exc), retry_at=now + backoff)
        return count

    async def _loop(self) -> None:
        assert self._stop is not None
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                # Keep ticker alive; errors are captured per-job in run log.
                pass
            await asyncio.sleep(self.tick_seconds)

