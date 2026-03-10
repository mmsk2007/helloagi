from dataclasses import dataclass, field
from typing import List, Literal
from agi_runtime.policies.packs import get_pack

Decision = Literal["allow", "escalate", "deny"]


@dataclass
class Policy:
    deny_keywords: List[str] = field(default_factory=lambda: [
        "at whatever cost",
        "harm",
        "bypass safeguards",
        "impersonate",
        "steal",
    ])
    escalate_keywords: List[str] = field(default_factory=lambda: [
        "finance", "medical", "legal", "delete", "production deploy"
    ])
    max_risk_allow: float = 0.45
    max_risk_escalate: float = 0.75


@dataclass
class GovernanceResult:
    decision: Decision
    risk: float
    reasons: List[str]


class SRGGovernor:
    """Deterministic runtime governance gate.

    Evaluates intent/action text and returns allow/escalate/deny.
    """

    def __init__(self, policy: Policy | None = None, policy_pack: str = "safe-default"):
        self.policy = policy or Policy()
        pack = get_pack(policy_pack)
        if not policy:
            self.policy.deny_keywords = pack.deny_keywords
            self.policy.escalate_keywords = pack.escalate_keywords

    def evaluate(self, text: str) -> GovernanceResult:
        t = text.lower()
        reasons: List[str] = []
        risk = 0.05

        for kw in self.policy.deny_keywords:
            if kw in t:
                risk += 0.7
                reasons.append(f"deny-keyword:{kw}")

        for kw in self.policy.escalate_keywords:
            if kw in t:
                risk += 0.22
                reasons.append(f"escalate-keyword:{kw}")

        risk = min(risk, 1.0)

        if risk > self.policy.max_risk_escalate:
            return GovernanceResult("deny", risk, reasons or ["high-risk"])
        if risk > self.policy.max_risk_allow:
            return GovernanceResult("escalate", risk, reasons or ["medium-risk"])
        return GovernanceResult("allow", risk, reasons or ["low-risk"])
