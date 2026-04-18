import time

from agi_runtime.reminders.store import ReminderStore


def test_store_create_list_update_remove(tmp_path):
    store = ReminderStore(path=str(tmp_path / "reminders.json"))
    now = time.time()
    job = store.create_job(
        principal_id="telegram:dm:1",
        chat_id="1",
        user_id="1",
        message="hello",
        schedule_kind="once",
        run_at=now + 60,
        cron_expr=None,
        timezone="UTC",
        next_run_at=now + 60,
    )
    jobs = store.list_jobs(principal_id="telegram:dm:1")
    assert len(jobs) == 1
    assert jobs[0].id == job.id

    store.update_job(job.id, enabled=False, last_status="paused")
    updated = store.get_job(job.id)
    assert updated and not updated.enabled

    assert store.remove_job(job.id) is True
    assert store.get_job(job.id) is None


def test_due_jobs_and_stuck_recovery(tmp_path):
    store = ReminderStore(path=str(tmp_path / "reminders.json"))
    now = time.time()
    job = store.create_job(
        principal_id="telegram:dm:1",
        chat_id="1",
        user_id="1",
        message="do now",
        schedule_kind="once",
        run_at=now - 2,
        cron_expr=None,
        timezone="UTC",
        next_run_at=now - 2,
    )
    store.update_job(job.id, running_at=now - 700)
    due = store.due_jobs(now_ts=now, stuck_seconds=600, oneshot_grace_seconds=300)
    assert any(j.id == job.id for j in due)

