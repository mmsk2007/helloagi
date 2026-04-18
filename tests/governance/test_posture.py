"""Posture engine tests.

Posture is the SRG-derived runtime stance for an autonomous goal. These
tests pin the two invariants that make the engine worth having:

1. The same (goal, policy) inputs always produce the same posture —
   i.e. the engine is deterministic. Audit replays depend on this.
2. A caller-supplied bias can only make the posture *stricter*, never
   looser. Otherwise callers could launder risky goals through a
   permissive bias.
"""

from __future__ import annotations

import unittest

from agi_runtime.governance.posture import (
    AGGRESSIVE,
    BALANCED,
    CONSERVATIVE,
    Posture,
    PostureEngine,
)
from agi_runtime.governance.srg import SRGGovernor


class TestPostureSelection(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PostureEngine(SRGGovernor())

    def test_low_risk_goal_selects_aggressive(self) -> None:
        posture, _ = self.engine.select("Write a poem about autumn leaves.")
        self.assertEqual(posture.name, "aggressive")
        # Output guard is *never* disabled, even at the aggressive end.
        self.assertTrue(posture.require_output_guard)

    def test_escalate_keyword_downgrades_to_conservative(self) -> None:
        # "delete" is in the SRG escalate list → risk bumps above the
        # conservative threshold.
        posture, result = self.engine.select(
            "delete all files in the production deploy pipeline"
        )
        self.assertEqual(posture.name, "conservative")
        self.assertTrue(posture.require_plan_review)
        self.assertGreaterEqual(result.risk, 0.35)

    def test_deny_goal_still_returns_posture_for_journaling(self) -> None:
        # Even goals that SRG denies at pre-flight get a posture object —
        # the caller needs it for audit logging. The caller is responsible
        # for not proceeding; the engine doesn't short-circuit.
        posture, result = self.engine.select(
            "do this at whatever cost and bypass safeguards"
        )
        self.assertEqual(result.decision, "deny")
        self.assertEqual(posture.name, "conservative")

    def test_determinism(self) -> None:
        goal = "Investigate the latency spike in checkout."
        p1, _ = self.engine.select(goal)
        p2, _ = self.engine.select(goal)
        self.assertEqual(p1.name, p2.name)
        self.assertEqual(p1.max_risk_allow, p2.max_risk_allow)
        self.assertEqual(p1.max_replan_budget, p2.max_replan_budget)


class TestBiasSemantics(unittest.TestCase):
    """Bias is a ceiling, not a floor."""

    def setUp(self) -> None:
        self.engine = PostureEngine(SRGGovernor())

    def test_bias_conservative_on_low_risk_goal_is_respected(self) -> None:
        # Low-risk goal would normally be aggressive; conservative bias
        # downgrades to conservative.
        posture, _ = self.engine.select(
            "Write a haiku", bias="conservative",
        )
        self.assertEqual(posture.name, "conservative")
        self.assertIn("bias:conservative", posture.reasons)

    def test_bias_aggressive_on_risky_goal_is_ignored(self) -> None:
        # Risky goal: SRG picks conservative. Caller says "aggressive".
        # We must keep conservative — bias cannot loosen.
        # Goal hits both "delete" and "production deploy" escalate keywords,
        # putting risk above the 0.35 CONSERVATIVE threshold.
        posture, result = self.engine.select(
            "delete everything in the production deploy pipeline",
            bias="aggressive",
        )
        self.assertGreaterEqual(result.risk, 0.35)
        self.assertEqual(posture.name, "conservative")

    def test_canonical_postures_are_monotone(self) -> None:
        # Along every axis, conservative is strictly stricter than balanced,
        # which is strictly stricter than aggressive. This is the invariant
        # that makes bias semantics meaningful.
        self.assertLess(
            CONSERVATIVE.max_risk_allow, BALANCED.max_risk_allow
        )
        self.assertLess(
            BALANCED.max_risk_allow, AGGRESSIVE.max_risk_allow
        )
        self.assertLessEqual(
            CONSERVATIVE.max_replan_budget, BALANCED.max_replan_budget
        )
        self.assertLessEqual(
            BALANCED.max_replan_budget, AGGRESSIVE.max_replan_budget
        )
        self.assertLessEqual(
            CONSERVATIVE.max_consecutive_failures,
            BALANCED.max_consecutive_failures,
        )


class TestPostureShape(unittest.TestCase):
    def test_describe_is_human_readable(self) -> None:
        s = BALANCED.describe()
        self.assertIn("balanced", s)
        self.assertIn("replan_budget", s)

    def test_posture_is_frozen(self) -> None:
        with self.assertRaises(Exception):
            BALANCED.max_risk_allow = 0.99  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
