from dataclasses import dataclass
from agi_runtime.governance.srg import SRGGovernor
from agi_runtime.latency.ale import ALEngine
from agi_runtime.memory.identity import IdentityEngine


@dataclass
class AgentResponse:
    text: str
    decision: str
    risk: float


class HelloAGIAgent:
    def __init__(self):
        self.governor = SRGGovernor()
        self.ale = ALEngine()
        self.identity = IdentityEngine()

    def think(self, user_input: str) -> AgentResponse:
        self.identity.evolve(user_input)

        gov = self.governor.evaluate(user_input)
        if gov.decision == "deny":
            return AgentResponse(
                text="I can’t help with unsafe or boundary-violating requests. I can help with a safe, high-impact alternative.",
                decision=gov.decision,
                risk=gov.risk,
            )

        cached = self.ale.get(user_input)
        if cached:
            return AgentResponse(text=cached, decision=gov.decision, risk=gov.risk)

        text = (
            f"[{self.identity.state.name} | {self.identity.state.character}] "
            f"Purpose: {self.identity.state.purpose}. "
            f"Plan: define objective, map constraints, execute measurable steps, verify outcomes."
        )
        if gov.decision == "escalate":
            text += " This request needs human confirmation before high-risk actions."

        self.ale.put(user_input, text)
        return AgentResponse(text=text, decision=gov.decision, risk=gov.risk)


# Backward compatibility
AGIRuntimeAgent = HelloAGIAgent
