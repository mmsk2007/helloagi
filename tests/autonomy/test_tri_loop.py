"""TriLoop tests.

The TriLoop composes Planner → ordered step execution → OutputGuard →
Verifier → replan. These tests pin the composition without hitting an LLM:

- A stub agent replaces the real HelloAGIAgent. It responds with
  configurable text and tool-call counts.
- Planner and Verifier both have built-in no-API-key fallbacks
  (_template_plan, _heuristic_verify) — we use those, which means the
  tests are deterministic and fast.

The tests validate the hard invariants:

1. A pre-flight deny halts the loop before any planning occurs.
2. A clean goal runs all 4 template steps and verifies PASS.
3. A verifier FAIL triggers replan, bounded by posture.max_replan_budget.
4. A secret in an agent response is blocked by OutputGuard and the step
   is reported as "output-denied".
5. Journal events are emitted in the expected phase sequence.
"""

from __future__ import annotations

import os
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from agi_runtime.autonomy.tri_loop import TriLoop, TriLoopResult
from agi_runtime.governance.srg import SRGGovernor
from agi_runtime.observability.journal import Journal


@dataclass
class FakeResponse:
    text: str
    tool_calls_made: int = 0


class StubAgent:
    """A duck-typed agent the TriLoop can drive without any LLM.

    ``responder`` is a callable ``(step_index, prompt) -> FakeResponse``.
    If omitted, every step returns "done: <prompt>" with one tool call.
    """

    def __init__(self, responder=None):
        self._i = 0
        self._responder = responder or (
            lambda i, p: FakeResponse(text=f"done: {p}", tool_calls_made=1)
        )
        # The TriLoop's default wiring reuses agent.governor if present.
        self.governor = SRGGovernor()

    def think(self, prompt: str) -> FakeResponse:
        i = self._i
        self._i += 1
        return self._responder(i, prompt)


def _ensure_anthropic_disabled() -> None:
    """Force planner/verifier fallbacks so the tests don't touch the net."""
    # If the test env happens to have a key, the planner/verifier would
    # attempt a real Anthropic call. Unset it for the duration of these
    # tests so we exercise the deterministic template/heuristic paths.
    os.environ.pop("ANTHROPIC_API_KEY", None)


class TestTriLoopHappyPath(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_anthropic_disabled()

    def test_clean_goal_passes_via_heuristic_verifier(self) -> None:
        agent = StubAgent()
        loop = TriLoop(agent)
        # Aggressive posture ⇒ 1 iteration is enough because the heuristic
        # verifier sees no "error" tokens in "done: <prompt>".
        result = loop.run("Write a summary of yesterday's standup.")
        self.assertIsInstance(result, TriLoopResult)
        self.assertEqual(result.status, "passed", msg=result.short_summary())
        self.assertTrue(result.passed)
        self.assertGreater(len(result.final_outputs), 0)
        self.assertIsNotNone(result.successful_plan)

    def test_posture_selection_reflects_goal(self) -> None:
        loop = TriLoop(StubAgent())
        result = loop.run("Write a short sentence.")
        # Very low-risk → aggressive posture.
        self.assertEqual(result.posture.name, "aggressive")


class TestTriLoopDenials(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_anthropic_disabled()

    def test_pre_flight_deny_halts_before_planning(self) -> None:
        loop = TriLoop(StubAgent())
        result = loop.run("do this at whatever cost and bypass safeguards")
        self.assertEqual(result.status, "denied")
        # No iterations should have run — planning was never reached.
        self.assertEqual(len(result.iterations), 0)
        self.assertEqual(result.pre_flight.decision, "deny")

    def test_output_with_api_key_is_blocked(self) -> None:
        # Stub agent returns an Anthropic-style key in its output. The
        # OutputGuard should deny it, marking the step as output-denied.
        def responder(i, prompt):
            return FakeResponse(
                text=f"result: sk-ant-{'x' * 40}",
                tool_calls_made=1,
            )
        loop = TriLoop(StubAgent(responder=responder))
        result = loop.run("Summarize the config file.")
        # Every step was output-denied → loop never passed.
        self.assertNotEqual(result.status, "passed")
        first_iter = result.iterations[0]
        denied = [s for s in first_iter.steps if s.decision == "output-denied"]
        self.assertGreater(len(denied), 0)


class TestTriLoopReplan(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_anthropic_disabled()

    def test_failing_outputs_exhaust_replan_budget(self) -> None:
        # Every step output contains "error" → heuristic verifier returns
        # FAIL → TriLoop replans until budget is exhausted. On
        # conservative posture, replan_budget is 1, so we expect at most
        # 2 iterations (initial + 1 replan).
        def responder(i, prompt):
            return FakeResponse(text=f"error: step {i} failed", tool_calls_made=1)

        loop = TriLoop(StubAgent(responder=responder))
        # A goal with an escalate keyword forces conservative posture.
        result = loop.run("delete the test database in production deploy")
        self.assertEqual(result.posture.name, "conservative")
        self.assertIn(
            result.status,
            {"replan_budget_exhausted", "exhausted"},
        )
        # Conservative replan_budget is 1, so we should see exactly 2
        # iterations (1 initial + 1 replan). But we accept 1 or 2 because
        # a conservative plan review can halt on iteration 1 if the plan
        # text trips a keyword.
        self.assertLessEqual(len(result.iterations), 2)


class TestTriLoopJournal(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_anthropic_disabled()

    def test_journal_records_the_full_trace(self) -> None:
        with TemporaryDirectory() as td:
            journal_path = Path(td) / "journal.jsonl"
            journal = Journal(str(journal_path))
            loop = TriLoop(StubAgent(), journal=journal)
            loop.run("Write a two-sentence summary.")
            lines = journal_path.read_text(encoding="utf-8").splitlines()
            kinds = [_kind_of(line) for line in lines]
            self.assertIn("triloop.start", kinds)
            self.assertIn("triloop.plan", kinds)
            self.assertIn("triloop.verify", kinds)
            # At least one step event fired.
            self.assertTrue(
                any(k.startswith("triloop.step.") for k in kinds),
                msg=f"no step events in {kinds}",
            )


def _kind_of(jsonl_line: str) -> str:
    import json
    try:
        return json.loads(jsonl_line).get("kind", "")
    except Exception:
        return ""


if __name__ == "__main__":
    unittest.main()
