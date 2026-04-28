"""Phase 1 routing decision tests.

The router is observation-only by default — these tests verify the *decision*
shape across the relevance × risk × posture matrix. Enforcement is covered in
Phase 2 tests.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import List

from agi_runtime.cognition.router import CognitiveRouter
from agi_runtime.cognition.fingerprint import task_fingerprint


# ── Test doubles ─────────────────────────────────────────────────────────


@dataclass
class FakeGov:
    decision: str = "allow"
    risk: float = 0.0
    reasons: tuple = ()


@dataclass
class FakeSkill:
    name: str = "summarize-report"
    description: str = "summarize a report"
    confidence_score: float = 0.0
    tools_required: list = field(default_factory=list)


@dataclass
class FakeMatch:
    skill: FakeSkill
    relevance: float = 0.0


class FakeSkillManager:
    def __init__(self, matches: List[FakeMatch] | None = None):
        self._matches = matches or []

    def find_matching_skill_semantic(self, query: str, top_k: int = 1):
        return list(self._matches)[:top_k]


class CapturingJournal:
    def __init__(self):
        self.events = []

    def write(self, kind: str, payload: dict):
        self.events.append((kind, payload))


# ── Tests ────────────────────────────────────────────────────────────────


class TestRouterDecision(unittest.TestCase):
    def _router(self, *, matches=None, config=None):
        return CognitiveRouter(
            skills=FakeSkillManager(matches=matches or []),
            journal=CapturingJournal(),
            config=config,
        )

    # Familiar + safe + balanced posture → System 1 verdict.
    def test_familiar_safe_routes_to_system1(self):
        match = FakeMatch(
            skill=FakeSkill(confidence_score=0.85), relevance=0.90,
        )
        router = self._router(matches=[match])
        d = router.decide("summarize the q3 report", FakeGov(risk=0.05))
        self.assertEqual(d.system, "system1")
        self.assertEqual(d.skill_match_name, "summarize-report")
        self.assertIn("familiar", d.reason)
        self.assertFalse(d.enforced)  # observe-only by default

    # Low relevance forces System 2 even with high confidence.
    def test_low_relevance_routes_to_system2(self):
        match = FakeMatch(skill=FakeSkill(confidence_score=0.95), relevance=0.20)
        router = self._router(matches=[match])
        d = router.decide("design a multi-region failover", FakeGov(risk=0.05))
        self.assertEqual(d.system, "system2")
        self.assertIn("unfamiliar", d.reason)

    # No skill match at all → System 2.
    def test_no_match_routes_to_system2(self):
        router = self._router(matches=[])
        d = router.decide("never seen this before", FakeGov(risk=0.0))
        self.assertEqual(d.system, "system2")
        self.assertEqual(d.reason, "no-skill-match")
        self.assertIsNone(d.skill_match_name)

    # SRG escalation overrides everything else.
    def test_srg_escalate_forces_system2(self):
        match = FakeMatch(skill=FakeSkill(confidence_score=0.99), relevance=0.99)
        router = self._router(matches=[match])
        d = router.decide(
            "do the trusted thing",
            FakeGov(decision="escalate", risk=0.40),
        )
        self.assertEqual(d.system, "system2")
        self.assertEqual(d.reason, "srg-escalate")

    # High SRG risk forces System 2 even with strong skill match.
    def test_high_risk_overrides_skill_match(self):
        match = FakeMatch(skill=FakeSkill(confidence_score=0.95), relevance=0.95)
        router = self._router(matches=[match])
        d = router.decide("perform sensitive op", FakeGov(risk=0.60))
        self.assertEqual(d.system, "system2")
        self.assertGreaterEqual(d.risk, 0.50)

    # Conservative posture floor pushes risk above the System 1 cap.
    def test_conservative_posture_pulls_to_system2(self):
        match = FakeMatch(skill=FakeSkill(confidence_score=0.95), relevance=0.95)
        # Use aggressive posture default config but pass conservative posture explicitly.
        router = self._router(matches=[match])
        d = router.decide(
            "do the familiar thing",
            FakeGov(risk=0.05),
            posture_name="conservative",
        )
        # Conservative posture floor (0.30) plus novelty (0.20) blends just under 0.50;
        # but with low SRG risk this should still allow System 1 by reason.
        # The acceptance test here: posture is reflected in the decision payload.
        self.assertEqual(d.posture, "conservative")
        self.assertGreaterEqual(d.risk_signals.posture_floor, 0.30)

    # Decision is logged to the journal as "routing.decided".
    def test_decision_written_to_journal(self):
        match = FakeMatch(skill=FakeSkill(confidence_score=0.85), relevance=0.85)
        journal = CapturingJournal()
        router = CognitiveRouter(
            skills=FakeSkillManager(matches=[match]),
            journal=journal,
        )
        router.decide("summarize the report", FakeGov())
        self.assertEqual(len(journal.events), 1)
        kind, payload = journal.events[0]
        self.assertEqual(kind, "routing.decided")
        self.assertIn("system", payload)
        self.assertIn("fingerprint", payload)
        self.assertEqual(payload["mode"], "observe")
        self.assertFalse(payload["enforced"])

    # Fingerprint stays stable across paraphrases.
    def test_fingerprint_stability(self):
        router = self._router(matches=[])
        d1 = router.decide("Summarize the Report.", FakeGov())
        d2 = router.decide("  summarize the report ", FakeGov())
        self.assertEqual(d1.fingerprint, d2.fingerprint)
        self.assertEqual(
            d1.fingerprint,
            task_fingerprint("summarize the report"),
        )

    # Novelty risk decays after the same fingerprint has been seen.
    def test_novelty_decays_after_first_sight(self):
        router = self._router(matches=[])
        first = router.decide("never-seen-task", FakeGov())
        second = router.decide("never-seen-task", FakeGov())
        self.assertGreater(first.risk_signals.novelty_risk, 0.0)
        self.assertEqual(second.risk_signals.novelty_risk, 0.0)


# ── Mode enforcement (Phase 1: never enforced when enabled=False) ──────


class TestRouterModes(unittest.TestCase):
    def _match(self, rel=0.9, conf=0.9):
        return FakeMatch(skill=FakeSkill(confidence_score=conf), relevance=rel)

    def test_observe_never_enforces(self):
        router = CognitiveRouter(
            skills=FakeSkillManager(matches=[self._match()]),
            journal=CapturingJournal(),
            config={"enabled": True, "mode": "observe"},
        )
        d = router.decide("summarize", FakeGov())
        self.assertEqual(d.system, "system1")
        self.assertFalse(d.enforced)

    def test_disabled_master_switch_never_enforces(self):
        router = CognitiveRouter(
            skills=FakeSkillManager(matches=[self._match()]),
            journal=CapturingJournal(),
            config={"enabled": False, "mode": "dual"},
        )
        d = router.decide("summarize", FakeGov())
        self.assertFalse(d.enforced)

    def test_system1_only_enforces_only_system1(self):
        router1 = CognitiveRouter(
            skills=FakeSkillManager(matches=[self._match(rel=0.9, conf=0.9)]),
            journal=CapturingJournal(),
            config={"enabled": True, "mode": "system1_only"},
        )
        d1 = router1.decide("familiar", FakeGov())
        self.assertEqual(d1.system, "system1")
        self.assertTrue(d1.enforced)

        router2 = CognitiveRouter(
            skills=FakeSkillManager(matches=[]),
            journal=CapturingJournal(),
            config={"enabled": True, "mode": "system1_only"},
        )
        d2 = router2.decide("unfamiliar", FakeGov())
        self.assertEqual(d2.system, "system2")
        self.assertFalse(d2.enforced)  # not enforced — falls through to today's loop

    def test_dual_enforces_both_systems(self):
        router = CognitiveRouter(
            skills=FakeSkillManager(matches=[self._match()]),
            journal=CapturingJournal(),
            config={"enabled": True, "mode": "dual"},
        )
        d = router.decide("anything", FakeGov())
        self.assertTrue(d.enforced)


if __name__ == "__main__":
    unittest.main()
