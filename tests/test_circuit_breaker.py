"""Tests for the circuit breaker module."""

import time
import unittest

from agi_runtime.robustness.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitStats,
    get_circuit_breaker,
)


class TestCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=0.1)

    def test_initial_state_is_closed(self):
        assert self.cb.can_execute("tool_a") is True
        status = self.cb.get_status("tool_a")
        assert status["state"] == "closed"

    def test_opens_after_threshold(self):
        for _ in range(3):
            self.cb.record_failure("tool_a")
        assert self.cb.can_execute("tool_a") is False
        assert self.cb.get_status("tool_a")["state"] == "open"

    def test_does_not_open_below_threshold(self):
        self.cb.record_failure("tool_a")
        self.cb.record_failure("tool_a")
        assert self.cb.can_execute("tool_a") is True

    def test_success_resets_failure_count(self):
        self.cb.record_failure("tool_a")
        self.cb.record_failure("tool_a")
        self.cb.record_success("tool_a")
        self.cb.record_failure("tool_a")
        self.cb.record_failure("tool_a")
        # Should NOT be open — success reset the counter
        assert self.cb.can_execute("tool_a") is True

    def test_half_open_after_cooldown(self):
        for _ in range(3):
            self.cb.record_failure("tool_a")
        assert self.cb.can_execute("tool_a") is False

        # Wait for cooldown
        time.sleep(0.15)
        assert self.cb.can_execute("tool_a") is True  # Half-open allows probe
        assert self.cb.get_status("tool_a")["state"] == "half_open"

    def test_half_open_success_closes(self):
        for _ in range(3):
            self.cb.record_failure("tool_a")
        time.sleep(0.15)
        self.cb.can_execute("tool_a")  # Transition to half-open
        self.cb.record_success("tool_a")
        assert self.cb.get_status("tool_a")["state"] == "closed"

    def test_half_open_failure_reopens(self):
        for _ in range(3):
            self.cb.record_failure("tool_a")
        time.sleep(0.15)
        self.cb.can_execute("tool_a")  # Transition to half-open
        self.cb.record_failure("tool_a")
        assert self.cb.get_status("tool_a")["state"] == "open"

    def test_independent_resources(self):
        for _ in range(3):
            self.cb.record_failure("tool_a")
        assert self.cb.can_execute("tool_a") is False
        assert self.cb.can_execute("tool_b") is True

    def test_reset(self):
        for _ in range(3):
            self.cb.record_failure("tool_a")
        self.cb.reset("tool_a")
        assert self.cb.can_execute("tool_a") is True
        assert self.cb.get_status("tool_a")["failures"] == 0

    def test_short_circuited_counter(self):
        for _ in range(3):
            self.cb.record_failure("tool_a")
        self.cb.can_execute("tool_a")  # increments short_circuited
        self.cb.can_execute("tool_a")
        assert self.cb.get_status("tool_a")["short_circuited"] == 2

    def test_get_all_status(self):
        self.cb.record_failure("tool_a")
        self.cb.record_success("tool_b")
        statuses = self.cb.get_all_status()
        assert len(statuses) == 2
        names = [s["resource"] for s in statuses]
        assert "tool_a" in names
        assert "tool_b" in names

    def test_global_instance(self):
        gb = get_circuit_breaker()
        assert isinstance(gb, CircuitBreaker)


if __name__ == "__main__":
    unittest.main()
