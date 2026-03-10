from dataclasses import dataclass
from agi_runtime.governance.srg import SRGGovernor
from agi_runtime.latency.ale import ALEngine
from agi_runtime.memory.identity import IdentityEngine
from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.tools.registry import ToolRegistry
from agi_runtime.observability.journal import Journal


@dataclass
class AgentResponse:
    text: str
    decision: str
    risk: float


class HelloAGIAgent:
    def __init__(self, settings: RuntimeSettings | None = None):
        self.settings = settings or RuntimeSettings()
        self.governor = SRGGovernor()
        self.ale = ALEngine()
        self.identity = IdentityEngine(
            path=self.settings.memory_path,
            mission=self.settings.mission,
            style=self.settings.style,
            domain_focus=self.settings.domain_focus,
        )
        self.tools = ToolRegistry()
        self.journal = Journal(self.settings.journal_path)

    def _maybe_run_tool(self, user_input: str) -> str | None:
        # convention: /tool <name> <text>
        if not user_input.startswith("/tool "):
            return None
        parts = user_input.split(" ", 2)
        if len(parts) < 2:
            return "Usage: /tool <plan|summarize|reflect> <text>"
        name = parts[1]
        payload = parts[2] if len(parts) > 2 else ""
        tr = self.tools.call(name, payload)
        return tr.output

    def think(self, user_input: str) -> AgentResponse:
        self.identity.evolve(user_input)
        self.journal.write("input", {"text": user_input})

        gov = self.governor.evaluate(user_input)
        if gov.decision == "deny":
            msg = "I can’t help with unsafe or boundary-violating requests. I can help with a safe, high-impact alternative."
            self.journal.write("deny", {"risk": gov.risk, "reasons": gov.reasons})
            return AgentResponse(text=msg, decision=gov.decision, risk=gov.risk)

        tool_output = self._maybe_run_tool(user_input)
        if tool_output:
            self.journal.write("tool", {"text": tool_output})
            return AgentResponse(text=tool_output, decision=gov.decision, risk=gov.risk)

        cached = self.ale.get(user_input)
        if cached:
            self.journal.write("cache_hit", {"text": cached})
            return AgentResponse(text=cached, decision=gov.decision, risk=gov.risk)

        text = (
            f"[{self.identity.state.name} | {self.identity.state.character}] "
            f"Purpose: {self.identity.state.purpose}. "
            f"Plan: define objective, map constraints, execute measurable steps, verify outcomes."
        )
        if gov.decision == "escalate":
            text += " This request needs human confirmation before high-risk actions."

        self.ale.put(user_input, text)
        self.journal.write("response", {"decision": gov.decision, "risk": gov.risk})
        return AgentResponse(text=text, decision=gov.decision, risk=gov.risk)


# Backward compatibility
AGIRuntimeAgent = HelloAGIAgent
