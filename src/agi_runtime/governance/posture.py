"""Posture engine — SRG-driven runtime stance selection.

Every autonomous run begins with a *posture*: the stance Hello AGI takes toward
the goal given its risk profile. Posture is not a user setting — it is an
SRG-derived output that scales:

- allow/escalate thresholds
- replan budget (how many times we're allowed to fail-and-retry)
- tolerance for consecutive failures before halting
- whether plan-level and output-level gates are mandatory

This is the missing link between the static policy-pack (which applies to a
whole session) and the dynamic, per-goal posture (which applies to a single
autonomous run). Posture is the shape SRG takes for *this specific task*.

Design principle: posture is *derived*, not *chosen by the caller*. Giving the
caller a dial defeats the governance model — the whole point is that SRG
decides the stance from the signal it sees in the goal. A caller can *bias*
posture (via ``bias``), but the final selection is SRG's to make.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from agi_runtime.governance.srg import GovernanceResult, SRGGovernor


PostureName = Literal["conservative", "balanced", "aggressive"]


@dataclass(frozen=True)
class Posture:
    """A runtime stance. Immutable for the duration of one autonomous run."""

    name: PostureName
    # SRG threshold overrides. Anything strictly > max_risk_allow requires
    # escalation; anything > max_risk_escalate is denied outright.
    max_risk_allow: float
    max_risk_escalate: float
    # How many times the tri-loop may replan before giving up.
    max_replan_budget: int
    # Consecutive failed steps tolerated before the current iteration halts.
    # "Consecutive" matters more than "total" because a streak of failures
    # usually indicates a structural problem the LLM can't recover from
    # without human input — this is the 3-strike escalation pattern from the
    # `generic` sibling project.
    max_consecutive_failures: int
    # Whether a plan, once produced, must re-pass SRG before execution begins.
    require_plan_review: bool
    # Whether tool / step outputs must pass OutputGuard before being accepted.
    # Defense-in-depth: input gates catch bad requests, output gates catch
    # leaked secrets and data exfiltration.
    require_output_guard: bool
    # Reasoning trail — *why* SRG chose this posture for this goal.
    reasons: tuple[str, ...] = ()

    def describe(self) -> str:
        return (
            f"Posture[{self.name}] "
            f"thresholds=({self.max_risk_allow:.2f}/{self.max_risk_escalate:.2f}) "
            f"replan_budget={self.max_replan_budget} "
            f"consec_fail_limit={self.max_consecutive_failures} "
            f"plan_review={self.require_plan_review} "
            f"output_guard={self.require_output_guard}"
        )


# Canonical postures. Tuned so that conservative is strictly stricter than
# balanced, which is strictly stricter than aggressive, along every axis.
CONSERVATIVE = Posture(
    name="conservative",
    max_risk_allow=0.25,
    max_risk_escalate=0.55,
    max_replan_budget=1,
    max_consecutive_failures=2,
    require_plan_review=True,
    require_output_guard=True,
)

BALANCED = Posture(
    name="balanced",
    max_risk_allow=0.45,
    max_risk_escalate=0.75,
    max_replan_budget=3,
    max_consecutive_failures=3,
    require_plan_review=True,
    require_output_guard=True,
)

AGGRESSIVE = Posture(
    name="aggressive",
    max_risk_allow=0.55,
    max_risk_escalate=0.85,
    max_replan_budget=5,
    max_consecutive_failures=5,
    require_plan_review=False,
    require_output_guard=True,  # output guard is *never* optional — secret
    # leakage is strictly worse than a missed plan review, so we keep it on
    # even at the aggressive end.
)


class PostureEngine:
    """Selects a Posture from a goal's SRG profile.

    The engine is deterministic — the same goal with the same policy pack
    always yields the same posture. This matters for audit replays.
    """

    def __init__(self, governor: Optional[SRGGovernor] = None):
        self.governor = governor or SRGGovernor()

    def select(
        self,
        goal_text: str,
        *,
        bias: Optional[PostureName] = None,
    ) -> tuple[Posture, GovernanceResult]:
        """Return (posture, srg_result_for_goal).

        `bias` is a *suggestion* from the caller (e.g., a policy pack with
        `identity_traits` like "aggressive-builder" may bias toward looser
        postures). The engine treats the bias as a ceiling, not a floor:
        SRG can always downgrade a biased posture if the goal is high-risk,
        but will not upgrade it beyond the bias.
        """
        result = self.governor.evaluate(goal_text)
        base = _posture_from_risk(result.risk)
        if bias is not None:
            base = _apply_bias(base, bias, result.risk)
        reasons = tuple([
            f"goal-risk:{result.risk:.2f}",
            *[f"reason:{r}" for r in result.reasons[:4]],
            f"chosen:{base.name}",
            *([f"bias:{bias}"] if bias else []),
        ])
        # Rebuild the posture with reasons attached (frozen dataclass).
        return (
            Posture(
                name=base.name,
                max_risk_allow=base.max_risk_allow,
                max_risk_escalate=base.max_risk_escalate,
                max_replan_budget=base.max_replan_budget,
                max_consecutive_failures=base.max_consecutive_failures,
                require_plan_review=base.require_plan_review,
                require_output_guard=base.require_output_guard,
                reasons=reasons,
            ),
            result,
        )


def _posture_from_risk(risk: float) -> Posture:
    """Map a raw SRG risk score to a canonical posture."""
    # Tight bands: even a whiff of elevated risk pulls us to conservative.
    # The moat is that we err toward less-capable-but-more-accountable over
    # more-capable-but-opaque.
    if risk >= 0.35:
        return CONSERVATIVE
    if risk >= 0.15:
        return BALANCED
    return AGGRESSIVE


def _apply_bias(base: Posture, bias: PostureName, risk: float) -> Posture:
    """Apply a caller bias, but only in the safer direction.

    A caller biasing "aggressive" on a high-risk goal is ignored — we can only
    downgrade, never upgrade. This is the "bias as ceiling" semantics.
    """
    order = {"conservative": 0, "balanced": 1, "aggressive": 2}
    # The base posture from risk is our *upper bound* on looseness.
    # A caller bias can only make us *stricter*, never looser.
    if order[bias] < order[base.name]:
        return {
            "conservative": CONSERVATIVE,
            "balanced": BALANCED,
            "aggressive": AGGRESSIVE,
        }[bias]
    return base


__all__ = [
    "Posture",
    "PostureName",
    "PostureEngine",
    "CONSERVATIVE",
    "BALANCED",
    "AGGRESSIVE",
]
