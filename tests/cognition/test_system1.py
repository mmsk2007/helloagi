"""Phase 2 — System 1 path tests.

Covers:
- ExpertOverrides construction from a routing decision (Haiku model, prompt
  addendum referencing the matched skill).
- ``prepare_expert_overrides`` returns None when the decision isn't an
  enforced System 1 — the agent must not silently swap models.
"""

import unittest
from dataclasses import dataclass

from agi_runtime.cognition.router import RoutingDecision
from agi_runtime.cognition.system1 import (
    EXPERT_MODEL_ID,
    ExpertOverrides,
    prepare_expert_overrides,
)


def _decision(
    *,
    system="system1",
    enforced=True,
    skill_name="check-followers",
    rel=0.92,
    conf=0.88,
):
    return RoutingDecision(
        system=system,
        reason="familiar (rel=0.92, conf=0.88)",
        fingerprint="abc123def4567890",
        posture="balanced",
        risk=0.10,
        skill_match_name=skill_name,
        skill_match_relevance=rel,
        skill_match_confidence=conf,
        srg_decision="allow",
        mode="system1_only",
        enforced=enforced,
    )


class TestPrepareExpertOverrides(unittest.TestCase):
    def test_enforced_system1_returns_overrides(self):
        ov = prepare_expert_overrides(_decision())
        self.assertIsNotNone(ov)
        self.assertEqual(ov.model_id, EXPERT_MODEL_ID)
        self.assertEqual(ov.skill_name, "check-followers")
        self.assertEqual(ov.fingerprint, "abc123def4567890")
        self.assertIn("check-followers", ov.prompt_addendum)
        self.assertIn("expert-mode", ov.prompt_addendum)

    def test_unenforced_returns_none(self):
        # Observe-mode decisions never trigger Expert Mode.
        d = _decision(enforced=False)
        self.assertIsNone(prepare_expert_overrides(d))

    def test_system2_returns_none(self):
        d = _decision(system="system2", skill_name=None)
        self.assertIsNone(prepare_expert_overrides(d))

    def test_no_skill_match_returns_none(self):
        # Defensive: even an enforced "system1" decision without a skill
        # should not fire Expert Mode silently.
        d = _decision(skill_name=None)
        self.assertIsNone(prepare_expert_overrides(d))

    def test_overrides_are_frozen(self):
        ov = prepare_expert_overrides(_decision())
        with self.assertRaises(Exception):
            ov.model_id = "claude-sonnet-4-6-20250514"  # type: ignore


if __name__ == "__main__":
    unittest.main()
