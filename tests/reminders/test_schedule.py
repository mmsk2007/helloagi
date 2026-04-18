from agi_runtime.reminders.schedule import ScheduleRequest, next_run_at, retry_backoff_seconds


def test_next_run_once():
    req = ScheduleRequest(kind="once", run_at=200.0, timezone="UTC")
    assert next_run_at(req, now_ts=100.0) == 200.0


def test_next_run_cron_future():
    req = ScheduleRequest(kind="cron", cron_expr="*/5 * * * *", timezone="UTC")
    nr = next_run_at(req, now_ts=1_700_000_000.0)
    assert nr is not None
    assert nr > 1_700_000_000.0


def test_retry_backoff_capped():
    assert retry_backoff_seconds(0) == 30.0
    assert retry_backoff_seconds(1) == 60.0
    assert retry_backoff_seconds(8) == 3600.0

