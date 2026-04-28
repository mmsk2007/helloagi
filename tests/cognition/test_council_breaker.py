"""Phase 5a — per-agent circuit breaker isolates flaky council voices.

The council should:
  - swallow agent exceptions (debate continues with an abstain turn)
  - count error-shaped abstains as breaker failures
  - short-circuit the agent after the breaker opens (no LLM calls)
  - probe back in once the cooldown expires
"""

import time
import unittest
from dataclasses import dataclass, field
from typing import List

from agi_runtime.cognition.system2.agents import (
    AgentTurn,
    PLANNER_ROLE,
    CRITIC_ROLE,
)
from agi_runtime.cognition.system2.debate import run_debate
from agi_runtime.cognition.system2.council import AgentCouncil
from agi_runtime.cognition.trace import DebateRound
from agi_runtime.robustness.circuit_breaker import CircuitBreaker


@dataclass
class _Recorder:
    name: str
    role: str = PLANNER_ROLE
    raises_on_call: bool = False
    error_critique: bool = False
    calls: int = 0

    def respond(self, *, user_input: str, prior_rounds: List[DebateRound]) -> AgentTurn:
        self.calls += 1
        if self.raises_on_call:
            raise RuntimeError("network down")
        if self.error_critique:
            return AgentTurn(
                agent=self.name, role=self.role, vote="abstain",
                output="", critique="client_error: timeout",
            )
        return AgentTurn(
            agent=self.name, role=self.role, vote="yes",
            output="ok", confidence=0.8,
        )


class TestBreakerInDebate(unittest.TestCase):
    def test_exception_does_not_break_debate(self):
        flaky = _Recorder("flaky", raises_on_call=True)
        ok = _Recorder("ok", role=CRITIC_ROLE)
        rounds = run_debate(
            user_input="task", agents=[flaky, ok], max_rounds=1,
        )
        self.assertEqual(len(rounds), 1)
        # Flaky vote captured as abstain, output empty.
        self.assertEqual(rounds[0].votes["flaky"], "abstain")
        self.assertEqual(rounds[0].votes["ok"], "yes")

    def test_breaker_opens_after_threshold_and_short_circuits(self):
        flaky = _Recorder("flaky", raises_on_call=True)
        breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=10.0)
        # Run two rounds — the breaker should open after the second failure.
        run_debate(user_input="task", agents=[flaky], max_rounds=1, breaker=breaker)
        run_debate(user_input="task", agents=[flaky], max_rounds=1, breaker=breaker)
        self.assertEqual(flaky.calls, 2)
        # Third round should NOT call the agent — circuit is open.
        run_debate(user_input="task", agents=[flaky], max_rounds=1, breaker=breaker)
        self.assertEqual(flaky.calls, 2)
        status = breaker.get_status("flaky")
        self.assertEqual(status["state"], "open")

    def test_error_critique_counts_as_failure(self):
        # No exceptions, but the agent returns the error-shaped abstain
        # produced by LLMCouncilAgent on parse / client failures.
        flaky = _Recorder("flaky", error_critique=True)
        breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=10.0)
        run_debate(user_input="t", agents=[flaky], max_rounds=1, breaker=breaker)
        run_debate(user_input="t", agents=[flaky], max_rounds=1, breaker=breaker)
        self.assertEqual(breaker.get_status("flaky")["state"], "open")

    def test_success_resets_failure_count(self):
        agent = _Recorder("a")
        breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=10.0)
        # One simulated failure...
        breaker.record_failure("a")
        run_debate(user_input="t", agents=[agent], max_rounds=1, breaker=breaker)
        # ...and the success should clear the failure counter.
        self.assertEqual(breaker.get_status("a")["failures"], 0)


class TestCouncilWithBreaker(unittest.TestCase):
    def test_council_supplies_default_breaker(self):
        agents = [_Recorder("a"), _Recorder("b", role=CRITIC_ROLE)]
        council = AgentCouncil(agents=agents, max_rounds=1)
        self.assertIsNotNone(council.breaker)
        outcome = council.deliberate(user_input="task", fingerprint="fp1")
        self.assertEqual(len(outcome.trace.rounds), 1)

    def test_council_isolates_flaky_agent_so_quorum_continues(self):
        flaky = _Recorder("flaky", raises_on_call=True)
        steady = _Recorder("steady", role=CRITIC_ROLE)
        breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=10.0)
        council = AgentCouncil(
            agents=[flaky, steady], max_rounds=2, breaker=breaker,
        )
        outcome = council.deliberate(user_input="task", fingerprint="fp1")
        # Flaky is abstaining; steady's "yes" carries the round.
        self.assertEqual(outcome.vote.winner, "yes")
        # After round 1 the breaker is open — round 2 short-circuits flaky.
        # So flaky's call count should not exceed 1.
        self.assertLessEqual(flaky.calls, 1)


if __name__ == "__main__":
    unittest.main()
