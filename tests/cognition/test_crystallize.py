"""SkillCrystallizer — Phase 4c gate logic.

We test the gate (min_successes × min_agreement), idempotency, and the
"don't crystallize" paths.  Trace store and skill bank are fakes —
we're not testing IO here, just the policy.
"""

import unittest
from typing import Dict, List, Optional

from agi_runtime.cognition.crystallize import SkillCrystallizer
from agi_runtime.cognition.trace import CouncilTrace, DebateRound
from agi_runtime.skills.skill_schema import SkillContract


class _FakeTraceStore:
    def __init__(self, traces: List[CouncilTrace]):
        self._traces = traces

    def find_by_fingerprint(self, fp: str) -> List[CouncilTrace]:
        return [t for t in self._traces if t.fingerprint == fp]


class _FakeSkillBank:
    def __init__(self):
        self.skills: Dict[str, SkillContract] = {}
        self.added: List[SkillContract] = []
        self.persisted: List[SkillContract] = []

    def add(self, skill: SkillContract) -> SkillContract:
        self.skills[skill.skill_id] = skill
        self.added.append(skill)
        return skill

    def persist(self, skill: SkillContract) -> None:
        self.skills[skill.skill_id] = skill
        self.persisted.append(skill)

    def get_by_name(self, name: str) -> Optional[SkillContract]:
        for s in self.skills.values():
            if s.name == name:
                return s
        return None

    def list_skills(self, **_kw) -> List[SkillContract]:
        return list(self.skills.values())


class _FakeJournal:
    def __init__(self):
        self.entries: List[tuple] = []

    def write(self, kind, payload):
        self.entries.append((kind, payload))


def _trace(fp: str, *, outcome="pass", votes=None, decision="step a;step b") -> CouncilTrace:
    if votes is None:
        votes = {"planner": "yes", "critic": "yes", "synthesizer": "yes"}
    return CouncilTrace(
        fingerprint=fp,
        user_input="goal X",
        rounds=[DebateRound(round_index=0, votes=dict(votes),
                            agent_outputs={"planner": "use browser_navigate"})],
        final_decision=decision,
        outcome=outcome,
    )


class TestCrystallizeGates(unittest.TestCase):
    def test_below_min_successes_does_not_crystallize(self):
        store = _FakeTraceStore([_trace("fp1"), _trace("fp1")])
        bank = _FakeSkillBank()
        crystallizer = SkillCrystallizer(
            trace_store=store, skill_bank=bank,
            min_council_successes=3, min_agent_agreement=0.66,
        )
        report = crystallizer.maybe_crystallize("fp1")
        self.assertFalse(report.crystallized)
        self.assertEqual(report.successes, 2)
        self.assertEqual(report.reason, "insufficient_successes")
        self.assertEqual(bank.added, [])

    def test_three_unanimous_passes_crystallizes(self):
        store = _FakeTraceStore([_trace("fp1") for _ in range(3)])
        bank = _FakeSkillBank()
        crystallizer = SkillCrystallizer(
            trace_store=store, skill_bank=bank,
            min_council_successes=3, min_agent_agreement=0.66,
        )
        report = crystallizer.maybe_crystallize("fp1")
        self.assertTrue(report.crystallized)
        self.assertEqual(report.reason, "created")
        self.assertEqual(len(bank.added), 1)
        skill = bank.added[0]
        self.assertEqual(skill.task_fingerprint, "fp1")
        self.assertEqual(skill.status, "candidate")

    def test_low_agreement_blocks_crystallization(self):
        # 1 yes vs 2 no on each → max/non_abstain = 0.66; we set the floor
        # higher to force a block.
        bad_votes = {"a": "yes", "b": "no", "c": "no"}
        traces = [_trace("fp2", votes=bad_votes) for _ in range(3)]
        store = _FakeTraceStore(traces)
        bank = _FakeSkillBank()
        crystallizer = SkillCrystallizer(
            trace_store=store, skill_bank=bank,
            min_council_successes=3, min_agent_agreement=0.85,
        )
        report = crystallizer.maybe_crystallize("fp2")
        self.assertFalse(report.crystallized)
        self.assertEqual(report.reason, "low_agreement")
        self.assertAlmostEqual(report.agreement, 2 / 3, places=2)

    def test_failed_traces_are_not_counted(self):
        traces = [
            _trace("fp3", outcome="pass"),
            _trace("fp3", outcome="fail"),
            _trace("fp3", outcome="fail"),
        ]
        store = _FakeTraceStore(traces)
        bank = _FakeSkillBank()
        crystallizer = SkillCrystallizer(
            trace_store=store, skill_bank=bank,
            min_council_successes=3, min_agent_agreement=0.66,
        )
        report = crystallizer.maybe_crystallize("fp3")
        self.assertEqual(report.successes, 1)
        self.assertFalse(report.crystallized)

    def test_missing_dependencies_short_circuit(self):
        crystallizer = SkillCrystallizer(trace_store=None, skill_bank=None)
        report = crystallizer.maybe_crystallize("fp_x")
        self.assertFalse(report.crystallized)
        self.assertEqual(report.reason, "missing_deps")

    def test_empty_fingerprint_short_circuits(self):
        store = _FakeTraceStore([])
        bank = _FakeSkillBank()
        crystallizer = SkillCrystallizer(trace_store=store, skill_bank=bank)
        report = crystallizer.maybe_crystallize("")
        self.assertFalse(report.crystallized)
        self.assertEqual(report.reason, "missing_deps")


class TestCrystallizeIdempotency(unittest.TestCase):
    def test_second_call_refreshes_instead_of_duplicating(self):
        store = _FakeTraceStore([_trace("fp1") for _ in range(3)])
        bank = _FakeSkillBank()
        crystallizer = SkillCrystallizer(
            trace_store=store, skill_bank=bank,
            min_council_successes=3, min_agent_agreement=0.66,
        )
        first = crystallizer.maybe_crystallize("fp1")
        self.assertTrue(first.crystallized)
        self.assertEqual(len(bank.added), 1)

        # Third pass arrives; recompute. Should refresh, not add again.
        store._traces.append(_trace("fp1"))
        second = crystallizer.maybe_crystallize("fp1")
        self.assertTrue(second.crystallized)
        self.assertEqual(second.reason, "refreshed")
        self.assertEqual(len(bank.added), 1)  # still one
        self.assertGreaterEqual(len(bank.persisted), 1)

    def test_refresh_bumps_confidence_floor(self):
        store = _FakeTraceStore([_trace("fp1") for _ in range(3)])
        bank = _FakeSkillBank()
        crystallizer = SkillCrystallizer(
            trace_store=store, skill_bank=bank,
            min_council_successes=3, min_agent_agreement=0.66,
        )
        crystallizer.maybe_crystallize("fp1")
        original = bank.added[0]
        original.confidence_score = 0.50  # simulate a drop

        # Add several more passes to push the floor higher.
        for _ in range(5):
            store._traces.append(_trace("fp1"))
        crystallizer.maybe_crystallize("fp1")
        self.assertGreater(original.confidence_score, 0.50)


class TestCrystallizeJournalling(unittest.TestCase):
    def test_skill_crystallized_event_emitted(self):
        store = _FakeTraceStore([_trace("fp1") for _ in range(3)])
        bank = _FakeSkillBank()
        journal = _FakeJournal()
        crystallizer = SkillCrystallizer(
            trace_store=store, skill_bank=bank, journal=journal,
            min_council_successes=3, min_agent_agreement=0.66,
        )
        crystallizer.maybe_crystallize("fp1")
        kinds = [k for k, _ in journal.entries]
        self.assertIn("skill.crystallized", kinds)


if __name__ == "__main__":
    unittest.main()
