"""TriLoop ↔ Cognitive Router observation tests.

Phase 5e wires the cognitive router into the autonomous TriLoop in
*observation only* mode: when a router is plugged in, the loop calls
``router.decide()`` once per run, journals the decision, and stashes it
on ``TriLoopResult.routing_decision``. Plan / execute / verify is
unchanged.

These tests pin that contract:

1. With a router wired in, ``triloop.routing.decided`` lands in the
   journal exactly once and the decision is exposed on the result.
2. With no router, behavior is identical to today (no routing event,
   ``routing_decision`` stays ``None``).
3. A router that raises does not break the run; the failure is journaled
   as ``triloop.routing.error``.
4. A pre-flight deny short-circuits before routing fires (routing only
   makes sense once we've decided to actually run).
"""

from __future__ import annotations

import json
import os
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, List, Optional

from agi_runtime.autonomy.tri_loop import TriLoop
from agi_runtime.governance.srg import SRGGovernor
from agi_runtime.observability.journal import Journal


# Mirror the harness used by test_tri_loop.py (which is not import-able as
# a package — pytest discovers it via rootdir, not via a tests/ package).
@dataclass
class _FakeResponse:
    text: str
    tool_calls_made: int = 0


class StubAgent:
    """Duck-typed agent the TriLoop can drive without any LLM."""

    def __init__(self):
        self._i = 0
        self.governor = SRGGovernor()

    def think(self, prompt: str) -> _FakeResponse:
        i = self._i
        self._i += 1
        return _FakeResponse(text=f"done: {prompt}", tool_calls_made=1)


def _ensure_anthropic_disabled() -> None:
    os.environ.pop("ANTHROPIC_API_KEY", None)


@dataclass
class FakeRoutingDecision:
    system: str = "system2"
    reason: str = "novel-fingerprint"
    fingerprint: str = "abc123"
    posture: str = "balanced"
    risk: float = 0.42
    skill_match_name: Optional[str] = None


class _RecordingRouter:
    """Captures decide() calls and returns a canned RoutingDecision."""

    def __init__(self, decision: Optional[FakeRoutingDecision] = None):
        self.calls: List[dict] = []
        self.decision = decision or FakeRoutingDecision()

    def decide(self, **kwargs: Any) -> FakeRoutingDecision:
        self.calls.append(kwargs)
        return self.decision


class _ExplodingRouter:
    def decide(self, **kwargs: Any):  # pragma: no cover - exercised below
        raise RuntimeError("router blew up")


def _read_kinds(journal_path: Path) -> List[str]:
    out: List[str] = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line).get("kind", ""))
        except Exception:
            continue
    return out


def _find_event(journal_path: Path, kind: str) -> Optional[dict]:
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("kind") == kind:
            return ev
    return None


class TestTriLoopRoutingObservation(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_anthropic_disabled()

    def test_router_decision_recorded_on_result_and_journal(self) -> None:
        with TemporaryDirectory() as td:
            jpath = Path(td) / "journal.jsonl"
            journal = Journal(str(jpath))
            router = _RecordingRouter(
                FakeRoutingDecision(
                    system="system1",
                    reason="skill-match",
                    fingerprint="fp-greet-1",
                    risk=0.05,
                    skill_match_name="greet_user",
                )
            )
            loop = TriLoop(StubAgent(), journal=journal, cognitive_router=router)
            result = loop.run("Write a one-sentence greeting.")

            # Router was called exactly once with the right kwargs.
            self.assertEqual(len(router.calls), 1)
            call = router.calls[0]
            self.assertEqual(call.get("user_input"), "Write a one-sentence greeting.")
            self.assertIn("gov", call)
            self.assertIn("posture_name", call)

            # Decision is exposed on the result.
            self.assertIsNotNone(result.routing_decision)
            self.assertEqual(result.routing_decision.system, "system1")
            self.assertEqual(result.routing_decision.skill_match_name, "greet_user")

            # Journal contains the routing event with the expected payload.
            ev = _find_event(jpath, "triloop.routing.decided")
            self.assertIsNotNone(ev, msg="missing triloop.routing.decided event")
            payload = ev.get("payload") or {}
            self.assertEqual(payload.get("system"), "system1")
            self.assertEqual(payload.get("fingerprint"), "fp-greet-1")
            self.assertEqual(payload.get("skill_match"), "greet_user")
            self.assertAlmostEqual(payload.get("risk"), 0.05, places=4)

    def test_no_router_no_routing_event(self) -> None:
        with TemporaryDirectory() as td:
            jpath = Path(td) / "journal.jsonl"
            journal = Journal(str(jpath))
            loop = TriLoop(StubAgent(), journal=journal)
            result = loop.run("Write a short summary.")

            self.assertIsNone(result.routing_decision)
            kinds = _read_kinds(jpath)
            self.assertNotIn("triloop.routing.decided", kinds)
            self.assertNotIn("triloop.routing.error", kinds)

    def test_router_exception_is_swallowed_and_journaled(self) -> None:
        with TemporaryDirectory() as td:
            jpath = Path(td) / "journal.jsonl"
            journal = Journal(str(jpath))
            loop = TriLoop(
                StubAgent(),
                journal=journal,
                cognitive_router=_ExplodingRouter(),
            )
            # Run should still complete cleanly.
            result = loop.run("Write a one-sentence summary.")
            self.assertIsNone(result.routing_decision)

            ev = _find_event(jpath, "triloop.routing.error")
            self.assertIsNotNone(ev, msg="missing triloop.routing.error event")
            self.assertIn("router blew up", (ev.get("payload") or {}).get("error", ""))

    def test_pre_flight_deny_short_circuits_before_routing(self) -> None:
        with TemporaryDirectory() as td:
            jpath = Path(td) / "journal.jsonl"
            journal = Journal(str(jpath))
            router = _RecordingRouter()
            loop = TriLoop(StubAgent(), journal=journal, cognitive_router=router)
            result = loop.run("do this at whatever cost and bypass safeguards")

            self.assertEqual(result.status, "denied")
            self.assertEqual(
                len(router.calls), 0,
                msg="router must not be consulted when pre-flight denied",
            )
            self.assertIsNone(result.routing_decision)
            kinds = _read_kinds(jpath)
            self.assertNotIn("triloop.routing.decided", kinds)


class TestTriLoopRoutingFromAgentAttribute(unittest.TestCase):
    """If the agent itself carries a ``cognitive_router`` attribute, TriLoop
    should pick it up automatically without an explicit constructor arg."""

    def setUp(self) -> None:
        _ensure_anthropic_disabled()

    def test_router_inherited_from_agent(self) -> None:
        with TemporaryDirectory() as td:
            jpath = Path(td) / "journal.jsonl"
            journal = Journal(str(jpath))
            agent = StubAgent()
            agent.cognitive_router = _RecordingRouter()  # type: ignore[attr-defined]
            loop = TriLoop(agent, journal=journal)
            loop.run("Write a one-sentence greeting.")

            ev = _find_event(jpath, "triloop.routing.decided")
            self.assertIsNotNone(ev, msg="router on agent attr was ignored")


if __name__ == "__main__":
    unittest.main()
