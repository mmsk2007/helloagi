import asyncio
import time

from agi_runtime.reminders.store import ReminderStore
from agi_runtime.reminders.ticker import ReminderTicker


def test_ticker_delivers_once_and_disables(tmp_path):
    store = ReminderStore(path=str(tmp_path / "reminders.json"))
    now = time.time()
    job = store.create_job(
        principal_id="telegram:dm:1",
        chat_id="1",
        user_id="1",
        message="hello",
        schedule_kind="once",
        run_at=now - 1,
        cron_expr=None,
        timezone="UTC",
        next_run_at=now - 1,
    )
    delivered = []

    async def dispatch(j):
        delivered.append(j.id)

    ticker = ReminderTicker(store=store, dispatch=dispatch, tick_seconds=1)
    count = asyncio.run(ticker.run_once())
    assert count == 1
    assert delivered == [job.id]
    updated = store.get_job(job.id)
    assert updated and not updated.enabled


def test_ticker_retry_backoff_on_failure(tmp_path):
    store = ReminderStore(path=str(tmp_path / "reminders.json"))
    now = time.time()
    job = store.create_job(
        principal_id="telegram:dm:1",
        chat_id="1",
        user_id="1",
        message="hello",
        schedule_kind="once",
        run_at=now - 1,
        cron_expr=None,
        timezone="UTC",
        next_run_at=now - 1,
    )

    async def dispatch(_):
        raise RuntimeError("dispatch failed")

    ticker = ReminderTicker(store=store, dispatch=dispatch, tick_seconds=1)
    asyncio.run(ticker.run_once())
    updated = store.get_job(job.id)
    assert updated is not None
    assert updated.last_status == "error"
    assert updated.next_run_at is not None and updated.next_run_at > now

