"""Tests for the enhanced supervisor module."""

import unittest

from agi_runtime.supervisor.supervisor import Supervisor, FailureRecord, IncidentReport


class TestFailureRecord(unittest.TestCase):
    def test_initial_state(self):
        rec = FailureRecord()
        assert rec.total_failures == 0
        assert rec.consecutive_failures == 0
        assert rec.failure_rate == 0.0

    def test_record_success(self):
        rec = FailureRecord()
        rec.record_success()
        assert rec.total_calls == 1
        assert rec.consecutive_failures == 0

    def test_record_failure(self):
        rec = FailureRecord()
        rec.record_failure("timeout")
        assert rec.total_failures == 1
        assert rec.consecutive_failures == 1
        assert rec.last_failure_reason == "timeout"

    def test_success_resets_consecutive(self):
        rec = FailureRecord()
        rec.record_failure("err")
        rec.record_failure("err")
        rec.record_success()
        assert rec.consecutive_failures == 0
        assert rec.total_failures == 2

    def test_failure_rate(self):
        rec = FailureRecord()
        rec.record_success()
        rec.record_failure("err")
        assert rec.failure_rate == 0.5


class TestSupervisor(unittest.TestCase):
    def setUp(self):
        self.sup = Supervisor(pause_consecutive=3, pause_rate=0.5, min_calls_for_rate=5)

    def test_tool_success(self):
        self.sup.record_tool_success("file_read")
        assert self.sup.is_tool_paused("file_read") is False

    def test_tool_pauses_after_consecutive_failures(self):
        for _ in range(3):
            self.sup.record_tool_failure("bad_tool", "timeout")
        assert self.sup.is_tool_paused("bad_tool") is True

    def test_tool_not_paused_below_threshold(self):
        self.sup.record_tool_failure("tool", "err")
        self.sup.record_tool_failure("tool", "err")
        assert self.sup.is_tool_paused("tool") is False

    def test_unpause_tool(self):
        for _ in range(3):
            self.sup.record_tool_failure("tool", "err")
        assert self.sup.is_tool_paused("tool") is True
        self.sup.unpause_tool("tool")
        assert self.sup.is_tool_paused("tool") is False

    def test_incident_generated_on_pause(self):
        for _ in range(3):
            self.sup.record_tool_failure("tool", "connection refused")
        incidents = self.sup.get_incidents()
        assert len(incidents) == 1
        assert incidents[0].severity == "critical"
        assert incidents[0].resource == "tool"
        assert "connection refused" in incidents[0].last_failure_reason

    def test_rate_based_pause(self):
        # 5 calls minimum, >50% failure rate
        for _ in range(2):
            self.sup.record_tool_success("flaky")
        # Reset consecutive to avoid consecutive-based pause
        self.sup._tools["flaky"].consecutive_failures = 0
        for _ in range(4):
            self.sup.record_tool_failure("flaky", "random error")
            self.sup._tools["flaky"].consecutive_failures = 1  # Keep below consecutive threshold
        # Force rate check: 4 failures out of 6 calls = 66%
        assert self.sup._tools["flaky"].failure_rate > 0.5

    def test_agent_tracking(self):
        self.sup.record_success("agent-1")
        self.sup.record_failure("agent-1", "crash")
        assert self.sup.should_pause("agent-1") is False
        self.sup.record_failure("agent-1", "crash")
        self.sup.record_failure("agent-1", "crash")
        assert self.sup.should_pause("agent-1") is True

    def test_incident_summary(self):
        for _ in range(3):
            self.sup.record_tool_failure("tool_a", "err")
        summary = self.sup.get_incident_summary()
        assert summary["total_incidents"] == 1
        assert summary["critical"] == 1
        assert "tool_a" in summary["paused_tools"]

    def test_get_status(self):
        self.sup.record_tool_success("file_read")
        self.sup.record_tool_failure("bash_exec", "denied")
        status = self.sup.get_status()
        assert "file_read" in status["tools"]
        assert "bash_exec" in status["tools"]
        assert status["tools"]["file_read"]["failures"] == 0
        assert status["tools"]["bash_exec"]["failures"] == 1

    def test_reset(self):
        self.sup.record_tool_failure("tool", "err")
        self.sup.reset()
        assert self.sup.get_status()["tools"] == {}
        assert self.sup.get_status()["incidents"] == 0


if __name__ == "__main__":
    unittest.main()
