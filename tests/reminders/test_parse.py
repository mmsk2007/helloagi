import time

import pytest

from agi_runtime.reminders.parse import parse_schedule_input


def test_parse_in_duration():
    now = 1_700_000_000.0
    parsed = parse_schedule_input("in 30m", timezone="UTC", now_ts=now)
    assert parsed.kind == "once"
    assert int(parsed.run_at - now) == 1800


def test_parse_tomorrow_time():
    now = time.time()
    parsed = parse_schedule_input("tomorrow 9am", timezone="UTC", now_ts=now)
    assert parsed.kind == "once"
    assert parsed.run_at > now


def test_parse_cron_expression():
    parsed = parse_schedule_input("cron:0 9 * * *", timezone="UTC")
    assert parsed.kind == "cron"
    assert parsed.cron_expr == "0 9 * * *"


def test_parse_invalid_schedule_raises():
    with pytest.raises(ValueError):
        parse_schedule_input("not-a-time-format", timezone="UTC")

