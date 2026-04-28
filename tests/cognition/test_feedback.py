"""Phase 2 — System 1 outcome feedback tests.

Verifies OutcomeRecorder updates:
- ``system1_success_count`` / ``system1_failure_count`` on the matched skill
- the skill's overall ``confidence_score`` (via record_success/record_failure)
- skill status auto-demotes to candidate if confidence drops past the floor
- a ``system1.outcome`` event lands in the journal each time
"""

import unittest

from agi_runtime.cognition.feedback import OutcomeRecorder
from agi_runtime.cognition.system1 import ExpertOverrides
from agi_runtime.skills.skill_schema import SkillContract


def _overrides(skill_name="check-followers"):
    return ExpertOverrides(
        model_id="claude-haiku-4-5-20251001",
        skill_name=skill_name,
        skill_relevance=0.9,
        skill_confidence=0.85,
        fingerprint="abc123def4567890",
        prompt_addendum="<expert-mode/>",
    )


class FakeBank:
    def __init__(self, contracts):
        self._by_name = {c.name: c for c in contracts}
        self.persisted = []

    def get_by_name(self, name):
        return self._by_name.get(name)

    def persist(self, contract):
        self.persisted.append(contract)


class FakeSkillManager:
    def __init__(self, contracts):
        self.skill_bank = FakeBank(contracts)


class CapturingJournal:
    def __init__(self):
        self.events = []

    def write(self, kind, payload):
        self.events.append((kind, payload))


def _new_skill(name, *, confidence=0.6, status="active", successes=4, failures=1):
    s = SkillContract(
        name=name,
        description="test",
        usage_count=successes + failures,
        success_count=successes,
        failure_count=failures,
        confidence_score=confidence,
        status=status,
    )
    return s


class TestOutcomeRecorderSystem1(unittest.TestCase):
    def test_success_increments_system1_counter(self):
        skill = _new_skill("check-followers")
        skills = FakeSkillManager([skill])
        journal = CapturingJournal()
        rec = OutcomeRecorder(skills=skills, journal=journal)

        report = rec.record_system1(_overrides(), success=True)

        self.assertTrue(report.success)
        self.assertEqual(skill.system1_success_count, 1)
        self.assertEqual(skill.system1_failure_count, 0)
        # Overall counters bumped via record_success.
        self.assertEqual(skill.success_count, 5)
        self.assertEqual(skill.usage_count, 6)
        # Persisted to the bank.
        self.assertEqual(len(skills.skill_bank.persisted), 1)
        # Journal has the outcome event.
        kinds = [k for k, _ in journal.events]
        self.assertIn("system1.outcome", kinds)

    def test_failure_increments_system1_failure_counter(self):
        skill = _new_skill("check-followers", confidence=0.55)
        rec = OutcomeRecorder(
            skills=FakeSkillManager([skill]),
            journal=CapturingJournal(),
        )
        rec.record_system1(_overrides(), success=False, failure_reason="max_turns")
        self.assertEqual(skill.system1_failure_count, 1)
        self.assertEqual(skill.failure_count, 2)
        self.assertTrue(any("system1:max_turns" in fm for fm in skill.failure_modes))

    def test_repeated_failure_demotes_active_skill_to_candidate(self):
        # A streak of System-1 failures should drag success_rate below the
        # demotion floor and flip the skill from active → candidate so
        # subsequent tasks bypass Expert Mode and go through the council.
        skill = _new_skill(
            "flaky-skill",
            confidence=0.30,
            status="active",
            successes=1,
            failures=3,
        )
        rec = OutcomeRecorder(
            skills=FakeSkillManager([skill]),
            journal=CapturingJournal(),
        )
        for _ in range(6):
            rec.record_system1(
                _overrides(skill_name="flaky-skill"),
                success=False,
                failure_reason="llm_error",
            )
        self.assertLess(skill.success_rate, 0.25)
        self.assertEqual(skill.status, "candidate")

    def test_success_after_failure_keeps_skill_active(self):
        skill = _new_skill("steady-skill", confidence=0.65)
        rec = OutcomeRecorder(
            skills=FakeSkillManager([skill]),
            journal=CapturingJournal(),
        )
        rec.record_system1(_overrides(skill_name="steady-skill"), success=False, failure_reason="x")
        rec.record_system1(_overrides(skill_name="steady-skill"), success=True)
        self.assertEqual(skill.status, "active")
        self.assertEqual(skill.system1_success_count, 1)
        self.assertEqual(skill.system1_failure_count, 1)

    def test_no_skill_in_bank_logs_but_does_not_crash(self):
        rec = OutcomeRecorder(
            skills=FakeSkillManager([]),  # empty bank
            journal=CapturingJournal(),
        )
        report = rec.record_system1(_overrides(), success=True)
        # Outcome was logged even though there was no contract to mutate.
        self.assertTrue(report.success)
        self.assertIsNone(report.new_confidence)


class TestOutcomeRecorderSystem2(unittest.TestCase):
    """Phase 3 — System 2 outcome flow.

    record_system2 must:
      - patch the trace's ``outcome`` via the trace store
      - emit ``system2.outcome`` to the journal with success/fail label
      - tolerate a missing trace store (graceful no-op)
    """

    def _trace(self, *, fingerprint="fp_x"):
        from agi_runtime.cognition.trace import CouncilTrace, DebateRound
        return CouncilTrace(
            fingerprint=fingerprint,
            user_input="check the followers",
            rounds=[DebateRound(round_index=0, agent_outputs={"planner": "use browser"})],
            final_decision="navigate to /profile",
            reasoning_summary="planner alone, consensus",
        )

    def test_success_marks_pass_and_journals(self):
        import tempfile
        from agi_runtime.cognition.trace import ThinkingTraceStore
        with tempfile.TemporaryDirectory() as tmp:
            store = ThinkingTraceStore(path=tmp)
            trace = self._trace()
            store.write(trace)
            journal = CapturingJournal()
            rec = OutcomeRecorder(
                skills=FakeSkillManager([]),
                journal=journal,
                trace_store=store,
            )
            report = rec.record_system2(trace, success=True)
            self.assertTrue(report.success)
            updated = store.get(trace.trace_id)
            self.assertEqual(updated.outcome, "pass")
            kinds = [k for k, _ in journal.events]
            self.assertIn("system2.outcome", kinds)

    def test_failure_marks_fail(self):
        import tempfile
        from agi_runtime.cognition.trace import ThinkingTraceStore
        with tempfile.TemporaryDirectory() as tmp:
            store = ThinkingTraceStore(path=tmp)
            trace = self._trace()
            store.write(trace)
            rec = OutcomeRecorder(
                skills=FakeSkillManager([]),
                journal=CapturingJournal(),
                trace_store=store,
            )
            rec.record_system2(trace, success=False, failure_reason="max_turns")
            self.assertEqual(store.get(trace.trace_id).outcome, "fail")

    def test_missing_trace_store_is_no_op(self):
        # No trace_store wired — recorder must still log + return cleanly.
        rec = OutcomeRecorder(
            skills=FakeSkillManager([]),
            journal=CapturingJournal(),
        )
        trace = self._trace()
        report = rec.record_system2(trace, success=True)
        self.assertTrue(report.success)

    def test_success_calls_crystallizer(self):
        import tempfile
        from agi_runtime.cognition.trace import ThinkingTraceStore
        calls = []

        class _Crystallizer:
            def maybe_crystallize(self, fp):
                calls.append(fp)

        with tempfile.TemporaryDirectory() as tmp:
            store = ThinkingTraceStore(path=tmp)
            trace = self._trace(fingerprint="fp_unique")
            store.write(trace)
            rec = OutcomeRecorder(
                skills=FakeSkillManager([]),
                journal=CapturingJournal(),
                trace_store=store,
                crystallizer=_Crystallizer(),
            )
            rec.record_system2(trace, success=True)
        self.assertEqual(calls, ["fp_unique"])

    def test_failure_does_not_call_crystallizer(self):
        import tempfile
        from agi_runtime.cognition.trace import ThinkingTraceStore
        calls = []

        class _Crystallizer:
            def maybe_crystallize(self, fp):
                calls.append(fp)

        with tempfile.TemporaryDirectory() as tmp:
            store = ThinkingTraceStore(path=tmp)
            trace = self._trace(fingerprint="fp_fail")
            store.write(trace)
            rec = OutcomeRecorder(
                skills=FakeSkillManager([]),
                journal=CapturingJournal(),
                trace_store=store,
                crystallizer=_Crystallizer(),
            )
            rec.record_system2(trace, success=False, failure_reason="bad")
        self.assertEqual(calls, [])

    def test_crystallizer_exception_does_not_break_recorder(self):
        import tempfile
        from agi_runtime.cognition.trace import ThinkingTraceStore

        class _ExplodingCrystallizer:
            def maybe_crystallize(self, fp):
                raise RuntimeError("disk full")

        with tempfile.TemporaryDirectory() as tmp:
            store = ThinkingTraceStore(path=tmp)
            trace = self._trace(fingerprint="fp_boom")
            store.write(trace)
            rec = OutcomeRecorder(
                skills=FakeSkillManager([]),
                journal=CapturingJournal(),
                trace_store=store,
                crystallizer=_ExplodingCrystallizer(),
            )
            report = rec.record_system2(trace, success=True)
            self.assertTrue(report.success)


if __name__ == "__main__":
    unittest.main()
