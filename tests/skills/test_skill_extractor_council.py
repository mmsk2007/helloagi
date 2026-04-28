"""SkillExtractor.extract_from_council_trace — Phase 4b coverage.

Round-trips a CouncilTrace into a SkillContract candidate so the
SkillCrystallizer (Phase 4c) has a clean unit to call.  We test:
  - happy path: trace with rounds + decision → contract with provenance
  - rejects empty / no-rounds / no_decision traces (returns None)
  - mines tool names from agent outputs
  - splits multi-step decisions on \n and ;
  - seeds confidence from inter-agent agreement
"""

import unittest

from agi_runtime.cognition.trace import CouncilTrace, DebateRound
from agi_runtime.skills.skill_extractor import SkillExtractor


def _make_trace(
    *,
    user_input: str = "Pull the latest follower count from the dashboard",
    final_decision: str = "browser_navigate to dashboard\nbrowser_screenshot the metrics card",
    reasoning_summary: str = "Two-step browser flow agreed by all four agents.",
    fingerprint: str = "fp_followers_v1",
    agent_outputs=None,
) -> CouncilTrace:
    if agent_outputs is None:
        agent_outputs = {
            "planner": "Use browser_navigate then browser_screenshot.",
            "critic": "Looks fine, but make sure browser_screenshot fires after the page loads.",
            "synthesizer": "Final: browser_navigate then browser_screenshot.",
        }
    rounds = [
        DebateRound(round_index=0, agent_outputs=dict(agent_outputs), votes={
            "planner": "yes", "critic": "yes", "synthesizer": "yes",
        }),
    ]
    return CouncilTrace(
        fingerprint=fingerprint,
        user_input=user_input,
        rounds=rounds,
        final_decision=final_decision,
        reasoning_summary=reasoning_summary,
    )


class TestExtractFromCouncilTrace(unittest.TestCase):
    def setUp(self):
        self.extractor = SkillExtractor()

    def test_happy_path_returns_contract(self):
        trace = _make_trace()
        skill = self.extractor.extract_from_council_trace(trace, agreement=1.0)
        self.assertIsNotNone(skill)
        self.assertEqual(skill.status, "candidate")
        self.assertEqual(skill.task_fingerprint, "fp_followers_v1")
        self.assertEqual(skill.council_origin_trace_id, trace.trace_id)
        self.assertIn("browser_navigate", skill.tools_required)
        self.assertIn("browser_screenshot", skill.tools_required)
        # Decision split into two steps.
        self.assertEqual(len(skill.execution_steps), 2)

    def test_returns_none_for_no_rounds(self):
        trace = CouncilTrace(
            fingerprint="fp_x",
            user_input="task",
            rounds=[],
            final_decision="anything",
        )
        self.assertIsNone(self.extractor.extract_from_council_trace(trace))

    def test_returns_none_for_no_decision_sentinel(self):
        trace = _make_trace(final_decision="no_decision")
        self.assertIsNone(self.extractor.extract_from_council_trace(trace))

    def test_returns_none_for_empty_decision(self):
        trace = _make_trace(final_decision="   ")
        self.assertIsNone(self.extractor.extract_from_council_trace(trace))

    def test_returns_none_for_none_trace(self):
        self.assertIsNone(self.extractor.extract_from_council_trace(None))

    def test_tools_mined_from_agent_outputs(self):
        trace = _make_trace(
            final_decision="run the workflow",
            agent_outputs={
                "planner": "First call web_search, then file_write the result.",
                "critic": "Make sure bash_exec is gated.",
                "synthesizer": "Confirmed.",
            },
        )
        skill = self.extractor.extract_from_council_trace(trace)
        self.assertIsNotNone(skill)
        self.assertIn("web_search", skill.tools_required)
        self.assertIn("file_write", skill.tools_required)
        self.assertIn("bash_exec", skill.tools_required)

    def test_decision_split_on_semicolons(self):
        trace = _make_trace(
            final_decision="step one; step two; step three",
        )
        skill = self.extractor.extract_from_council_trace(trace)
        self.assertEqual(len(skill.execution_steps), 3)
        self.assertEqual(skill.execution_steps[0], "step one")

    def test_single_step_decision_is_kept(self):
        trace = _make_trace(final_decision="just one move")
        skill = self.extractor.extract_from_council_trace(trace)
        self.assertEqual(skill.execution_steps, ["just one move"])

    def test_decision_steps_capped_at_15(self):
        decision = ";".join(f"step {i}" for i in range(40))
        trace = _make_trace(final_decision=decision)
        skill = self.extractor.extract_from_council_trace(trace)
        self.assertEqual(len(skill.execution_steps), 15)

    def test_user_input_falls_back_to_decision(self):
        trace = _make_trace(user_input="")
        skill = self.extractor.extract_from_council_trace(trace, agreement=0.8)
        self.assertIsNotNone(skill)
        self.assertTrue(skill.name)  # Derived from final_decision

    def test_summary_pulled_into_success_criteria(self):
        trace = _make_trace(reasoning_summary="Council unanimous on browser flow.")
        skill = self.extractor.extract_from_council_trace(trace)
        self.assertIn("Council unanimous on browser flow.", skill.success_criteria)


class TestSeedConfidence(unittest.TestCase):
    def test_default_when_no_agreement(self):
        self.assertEqual(SkillExtractor._seed_confidence(None), 0.6)

    def test_floor_at_two_thirds_agreement(self):
        # 0.66 → 0.55 by design.
        self.assertAlmostEqual(SkillExtractor._seed_confidence(0.66), 0.55, places=2)

    def test_unanimous_caps_higher(self):
        # 1.0 → 0.7
        self.assertAlmostEqual(SkillExtractor._seed_confidence(1.0), 0.7, places=2)

    def test_clamps_negative_to_floor(self):
        # Below 0.66 still gives a sane number (extrapolated, but bounded by clamp).
        v = SkillExtractor._seed_confidence(-0.5)
        self.assertGreaterEqual(v, 0.0)
        self.assertLessEqual(v, 1.0)

    def test_clamps_above_one(self):
        v = SkillExtractor._seed_confidence(2.0)
        self.assertLessEqual(v, 1.0)


if __name__ == "__main__":
    unittest.main()
