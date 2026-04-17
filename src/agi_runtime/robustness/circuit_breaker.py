"""Circuit breaker pattern for tool and provider failure protection.

Prevents cascading failures by tracking consecutive failures
and temporarily disabling problematic tools/providers.

States:
  CLOSED  — Normal operation, requests flow through
  OPEN    — Too many failures, requests short-circuited
  HALF_OPEN — Cooldown expired, allow one probe request
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitStats:
    failures: int = 0
    successes: int = 0
    last_failure_time: float = 0
    state: CircuitState = CircuitState.CLOSED
    total_short_circuited: int = 0


class CircuitBreaker:
    """Per-resource circuit breaker.

    After `failure_threshold` consecutive failures, opens the circuit.
    After `cooldown_seconds`, transitions to half-open for a probe.
    A successful probe closes the circuit; a failed probe re-opens it.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        success_threshold: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.success_threshold = success_threshold
        self._circuits: Dict[str, CircuitStats] = {}

    def _get(self, resource: str) -> CircuitStats:
        if resource not in self._circuits:
            self._circuits[resource] = CircuitStats()
        return self._circuits[resource]

    def can_execute(self, resource: str) -> bool:
        """Check if a request to this resource should be allowed."""
        stats = self._get(resource)

        if stats.state == CircuitState.CLOSED:
            return True

        if stats.state == CircuitState.OPEN:
            # Check if cooldown has expired
            if time.time() - stats.last_failure_time >= self.cooldown_seconds:
                stats.state = CircuitState.HALF_OPEN
                return True  # Allow probe
            stats.total_short_circuited += 1
            return False

        if stats.state == CircuitState.HALF_OPEN:
            return True  # Allow probe

        return True

    def record_success(self, resource: str):
        """Record a successful execution."""
        stats = self._get(resource)
        stats.successes += 1

        if stats.state == CircuitState.HALF_OPEN:
            # Probe succeeded — close the circuit
            stats.state = CircuitState.CLOSED
            stats.failures = 0

        elif stats.state == CircuitState.CLOSED:
            stats.failures = 0  # Reset failure counter on success

    def record_failure(self, resource: str):
        """Record a failed execution."""
        stats = self._get(resource)
        stats.failures += 1
        stats.last_failure_time = time.time()

        if stats.state == CircuitState.HALF_OPEN:
            # Probe failed — re-open
            stats.state = CircuitState.OPEN

        elif stats.state == CircuitState.CLOSED:
            if stats.failures >= self.failure_threshold:
                stats.state = CircuitState.OPEN

    def get_status(self, resource: str) -> dict:
        """Get circuit status for a resource."""
        stats = self._get(resource)
        return {
            "resource": resource,
            "state": stats.state.value,
            "failures": stats.failures,
            "successes": stats.successes,
            "short_circuited": stats.total_short_circuited,
        }

    def get_all_status(self) -> list:
        """Get status for all tracked resources."""
        return [self.get_status(r) for r in sorted(self._circuits.keys())]

    def reset(self, resource: str):
        """Manually reset a circuit to closed state."""
        if resource in self._circuits:
            self._circuits[resource] = CircuitStats()


# Global instance
_global_breaker = CircuitBreaker()


def get_circuit_breaker() -> CircuitBreaker:
    return _global_breaker
