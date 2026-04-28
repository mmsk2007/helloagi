"""Risk scoring for routing decisions.

Combines four signals into a single 0..1 risk number that the router uses to
decide whether System 1 (Expert) is safe enough or whether we must escalate
to System 2 (Thinking):

  - srg_risk      — what SRG already computed for the input (authoritative)
  - posture_floor — conservative postures pull risk up
  - tool_health   — open circuit breakers raise risk for skill-suggested tools
  - novelty       — never-before-seen fingerprints are riskier than familiar ones

The blend is intentionally explicit (not learned) — Phase 1 prioritizes
auditability over sophistication. We can swap in a learned scorer later
without touching callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from agi_runtime.governance.srg import GovernanceResult
from agi_runtime.robustness.circuit_breaker import CircuitBreaker, CircuitState


@dataclass
class RiskSignals:
    """Inputs to the risk score, kept for journaling/audit."""

    srg_risk: float = 0.0
    posture_floor: float = 0.0
    tool_health_risk: float = 0.0
    novelty_risk: float = 0.0
    contributing: list[str] = field(default_factory=list)


# Posture name → minimum risk floor.
# A conservative posture should never let System 1 fire on a "trivial" task
# without at least *some* deliberation.
_POSTURE_FLOORS = {
    "conservative": 0.30,
    "balanced": 0.10,
    "aggressive": 0.0,
}


class RiskScorer:
    """Deterministic risk-signal blender.

    Output is clamped to [0, 1]. The score is *not* a probability — it's a
    routing signal, comparable across calls but not interpretable on its own.
    """

    def __init__(self, circuit_breaker: Optional[CircuitBreaker] = None):
        self._breaker = circuit_breaker

    def score(
        self,
        gov: GovernanceResult,
        *,
        posture_name: str = "balanced",
        suggested_tools: Optional[Iterable[str]] = None,
        is_novel: bool = True,
    ) -> tuple[float, RiskSignals]:
        signals = RiskSignals()
        contributing: list[str] = []

        signals.srg_risk = max(0.0, min(1.0, float(getattr(gov, "risk", 0.0) or 0.0)))
        if signals.srg_risk > 0:
            contributing.append(f"srg={signals.srg_risk:.2f}")

        signals.posture_floor = _POSTURE_FLOORS.get(posture_name, 0.10)
        if signals.posture_floor > 0:
            contributing.append(f"posture={posture_name}:{signals.posture_floor:.2f}")

        signals.tool_health_risk = self._tool_health(suggested_tools)
        if signals.tool_health_risk > 0:
            contributing.append(f"tool-health={signals.tool_health_risk:.2f}")

        signals.novelty_risk = 0.20 if is_novel else 0.0
        if signals.novelty_risk > 0:
            contributing.append("novel-fingerprint")

        # Blend: the highest single signal dominates, but additional signals
        # nudge the score up. This matches the auditability goal — one big
        # risk source can't be diluted by many tiny ones.
        primary = max(
            signals.srg_risk,
            signals.posture_floor,
            signals.tool_health_risk,
            signals.novelty_risk,
        )
        secondary = (
            signals.srg_risk
            + signals.posture_floor
            + signals.tool_health_risk
            + signals.novelty_risk
            - primary
        )
        score = min(1.0, primary + 0.25 * secondary)
        signals.contributing = contributing
        return round(score, 3), signals

    def _tool_health(self, tools: Optional[Iterable[str]]) -> float:
        if not tools or self._breaker is None:
            return 0.0
        worst = 0.0
        for tool in tools:
            status = self._breaker.get_status(tool)
            state = status.get("state")
            failures = int(status.get("failures") or 0)
            if state == CircuitState.OPEN.value:
                worst = max(worst, 0.6)
            elif state == CircuitState.HALF_OPEN.value:
                worst = max(worst, 0.4)
            elif failures >= 2:
                worst = max(worst, 0.2)
        return worst


__all__ = ["RiskScorer", "RiskSignals"]
