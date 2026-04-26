"""Skill Evaluator — scoring, decay, promotion, retirement, refinement.

Manages the full lifecycle of skills in the bank: computes confidence
scores, applies time-based decay, promotes high-performers, retires
low-performers, and refines skills on failure.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

from agi_runtime.skills.skill_schema import SkillContract
from agi_runtime.skills.skill_bank import SkillBank


@dataclass
class EvaluationResult:
    """Result of evaluating a skill's lifecycle state."""
    skill_id: str
    action: str  # "promoted", "retired", "decayed", "refined", "unchanged"
    old_confidence: float
    new_confidence: float
    reason: str


class SkillEvaluator:
    """Lifecycle evaluator for the skill bank."""

    PROMOTE_THRESHOLD = 0.7       # Promote candidate → active
    PROMOTE_MIN_USES = 3          # Minimum uses before promotion
    RETIRE_THRESHOLD = 0.15       # Retire below this confidence
    DECAY_RATE_PER_DAY = 0.005    # Daily confidence decay for unused skills
    MAX_DECAY = 0.3               # Maximum decay before stabilization

    def __init__(self, bank: SkillBank):
        self.bank = bank

    # ── Evaluate All Skills ──────────────────────────────────────

    def evaluate_all(self) -> List[EvaluationResult]:
        """Run lifecycle evaluation on all skills in the bank."""
        results: List[EvaluationResult] = []
        for skill in self.bank.list_skills():
            result = self._evaluate_one(skill)
            if result:
                results.append(result)
        return results

    def _evaluate_one(self, skill: SkillContract) -> Optional[EvaluationResult]:
        """Evaluate a single skill's lifecycle state."""
        old_conf = skill.confidence_score

        # Auto-promote candidates with enough successful uses
        if skill.status == "candidate":
            if (skill.usage_count >= self.PROMOTE_MIN_USES
                    and skill.confidence_score >= self.PROMOTE_THRESHOLD):
                self.bank.promote(skill.skill_id)
                return EvaluationResult(
                    skill_id=skill.skill_id,
                    action="promoted",
                    old_confidence=old_conf,
                    new_confidence=skill.confidence_score,
                    reason=f"Uses={skill.usage_count}, conf={old_conf:.2f} >= {self.PROMOTE_THRESHOLD}",
                )

        # Auto-retire low-confidence active skills
        if skill.status in ("active", "candidate"):
            if skill.confidence_score < self.RETIRE_THRESHOLD and skill.usage_count >= 5:
                self.bank.retire(skill.skill_id)
                return EvaluationResult(
                    skill_id=skill.skill_id,
                    action="retired",
                    old_confidence=old_conf,
                    new_confidence=skill.confidence_score,
                    reason=f"Conf {old_conf:.2f} < {self.RETIRE_THRESHOLD} with {skill.usage_count} uses",
                )

        # Apply time-based decay
        if skill.status in ("active", "candidate") and skill.last_used_at:
            days_idle = (time.time() - skill.last_used_at) / 86400
            if days_idle > 7:
                decay = min(self.DECAY_RATE_PER_DAY * days_idle, self.MAX_DECAY)
                new_conf = max(0.0, round(skill.confidence_score - decay, 3))
                if new_conf != skill.confidence_score:
                    skill.confidence_score = new_conf
                    self.bank.update(skill)
                    return EvaluationResult(
                        skill_id=skill.skill_id,
                        action="decayed",
                        old_confidence=old_conf,
                        new_confidence=new_conf,
                        reason=f"Idle {days_idle:.0f} days, decayed by {decay:.3f}",
                    )

        return None

    # ── Record outcome and refine ────────────────────────────────

    def record_invocation(
        self,
        skill_id: str,
        success: bool,
        failure_mode: str = "",
        recovery_note: str = "",
    ) -> Optional[EvaluationResult]:
        """Record a skill invocation outcome and update the skill."""
        skill = self.bank.get(skill_id)
        if not skill:
            return None

        old_conf = skill.confidence_score
        if success:
            skill.record_success()
            action = "unchanged"
        else:
            skill.record_failure(failure_mode)
            action = "refined"
            # Add recovery note if provided
            if recovery_note and recovery_note not in (skill.recovery_strategy or ""):
                if skill.recovery_strategy:
                    skill.recovery_strategy += f"; {recovery_note}"
                else:
                    skill.recovery_strategy = recovery_note

        self.bank.update(skill)
        return EvaluationResult(
            skill_id=skill.skill_id,
            action=action,
            old_confidence=old_conf,
            new_confidence=skill.confidence_score,
            reason=f"{'Success' if success else 'Failure'}: {failure_mode or 'ok'}",
        )

    # ── Bulk operations ──────────────────────────────────────────

    def get_promotion_candidates(self) -> List[SkillContract]:
        """Get skills that are ready for promotion."""
        return [
            s for s in self.bank.list_skills(status="candidate")
            if s.usage_count >= self.PROMOTE_MIN_USES
            and s.confidence_score >= self.PROMOTE_THRESHOLD
        ]

    def get_retirement_candidates(self) -> List[SkillContract]:
        """Get skills that should be retired."""
        return [
            s for s in self.bank.list_skills()
            if s.status in ("active", "candidate")
            and s.confidence_score < self.RETIRE_THRESHOLD
            and s.usage_count >= 5
        ]


__all__ = ["SkillEvaluator", "EvaluationResult"]
