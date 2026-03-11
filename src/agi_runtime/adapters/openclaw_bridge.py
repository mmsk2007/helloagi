"""OpenClaw bridge — makes HelloAGI a fully governed Claude Agent SDK agent.

Architecture
------------
1. Governance gate (SRG) runs *before* any LLM call — deny returns immediately.
2. HelloAGI tools (plan, summarize, reflect, governance_check) are exposed to the
   Claude Agent SDK as an in-process MCP server so Claude can invoke them.
3. The Claude Agent SDK runs claude-opus-4-6 with the HelloAGI tools available.
4. All interactions are journaled via the observability layer.
5. ALE cache is checked before the SDK call and populated on the way out.

Usage
-----
    import anyio
    from agi_runtime.adapters.openclaw_bridge import run_openclaw_agent

    task = anyio.run(run_openclaw_agent, "Help me plan a new agent product")
    print(task.summary)
"""
from __future__ import annotations

from dataclasses import dataclass

from agi_runtime.governance.srg import SRGGovernor
from agi_runtime.latency.ale import ALEngine
from agi_runtime.memory.identity import IdentityEngine
from agi_runtime.observability.journal import Journal
from agi_runtime.tools.registry import ToolRegistry
from agi_runtime.config.settings import RuntimeSettings, load_settings

try:
    from claude_agent_sdk import (
        tool,
        create_sdk_mcp_server,
        ClaudeSDKClient,
        ClaudeAgentOptions,
        ResultMessage,
    )
    _SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SDK_AVAILABLE = False


# ---------------------------------------------------------------------------
# Core data types (kept stable — used by the rest of the codebase)
# ---------------------------------------------------------------------------

@dataclass
class OpenClawTask:
    summary: str
    requires_human_confirm: bool = False


def to_openclaw_task(response_text: str, decision: str) -> OpenClawTask:
    return OpenClawTask(
        summary=response_text,
        requires_human_confirm=(decision == "escalate"),
    )


# ---------------------------------------------------------------------------
# HelloAGI tools for the Claude Agent SDK
# These are registered as an in-process MCP server so Claude can call them.
# ---------------------------------------------------------------------------

_shared_tools = ToolRegistry()
_shared_governor = SRGGovernor()


if _SDK_AVAILABLE:
    @tool(
        "agi_plan",
        "Generate a structured step-by-step action plan for a goal or objective",
        {"goal": str},
    )
    async def _tool_agi_plan(args: dict) -> dict:
        result = _shared_tools.call("plan", args.get("goal", ""))
        return {"content": [{"type": "text", "text": result.output}]}

    @tool(
        "agi_summarize",
        "Summarize a long text down to its most essential points",
        {"text": str},
    )
    async def _tool_agi_summarize(args: dict) -> dict:
        result = _shared_tools.call("summarize", args.get("text", ""))
        return {"content": [{"type": "text", "text": result.output}]}

    @tool(
        "agi_reflect",
        "Generate a reflection prompt: what worked, what failed, what to try next",
        {"context": str},
    )
    async def _tool_agi_reflect(args: dict) -> dict:
        result = _shared_tools.call("reflect", args.get("context", ""))
        return {"content": [{"type": "text", "text": result.output}]}

    @tool(
        "agi_governance_check",
        "Run the SRG governance gate on a proposed action or text to get allow/escalate/deny",
        {"text": str},
    )
    async def _tool_agi_governance_check(args: dict) -> dict:
        gov = _shared_governor.evaluate(args.get("text", ""))
        return {
            "content": [{
                "type": "text",
                "text": f"decision={gov.decision} risk={gov.risk:.2f} reasons={gov.reasons}",
            }]
        }

    _helloagi_mcp_server = create_sdk_mcp_server(
        "helloagi-tools",
        tools=[
            _tool_agi_plan,
            _tool_agi_summarize,
            _tool_agi_reflect,
            _tool_agi_governance_check,
        ],
    )


# ---------------------------------------------------------------------------
# OpenClawAgent — the main agent class
# ---------------------------------------------------------------------------

class OpenClawAgent:
    """Governed Claude Agent SDK agent backed by HelloAGI infrastructure."""

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
        self.journal = Journal(self.settings.journal_path)

    def _system_prompt(self) -> str:
        s = self.identity.state
        principles = "; ".join(s.principles)
        return (
            f"You are {s.name}, a {s.character}.\n"
            f"Purpose: {s.purpose}\n"
            f"Principles: {principles}\n"
            f"Style: {self.settings.style}\n"
            f"Domain focus: {self.settings.domain_focus}\n\n"
            "You have access to HelloAGI tools:\n"
            "- agi_plan: structured action planning\n"
            "- agi_summarize: distill text to essentials\n"
            "- agi_reflect: retrospective analysis\n"
            "- agi_governance_check: validate safety before acting\n\n"
            "Always be direct, practical, and actionable. "
            "Use agi_governance_check when uncertain about the safety of an action."
        )

    async def run(self, prompt: str) -> OpenClawTask:
        """Run the governed openclaw agent for a given prompt."""
        # 1. Governance gate — runs before any SDK/LLM call
        gov = self.governor.evaluate(prompt)
        self.journal.write("openclaw_input", {"prompt": prompt, "gov_decision": gov.decision, "risk": gov.risk})

        if gov.decision == "deny":
            summary = (
                "Request denied by governance gate. "
                f"Risk={gov.risk:.2f}. Reasons: {', '.join(gov.reasons)}. "
                "I can help with a safe, high-impact alternative instead."
            )
            self.journal.write("openclaw_deny", {"risk": gov.risk, "reasons": gov.reasons})
            return OpenClawTask(summary=summary, requires_human_confirm=False)

        # 2. ALE cache check
        cached = self.ale.get(prompt)
        if cached:
            self.journal.write("openclaw_cache_hit", {"text": cached})
            return to_openclaw_task(cached, gov.decision)

        # 3. Graceful degradation when SDK not installed
        if not _SDK_AVAILABLE:
            fallback = (
                f"[{self.identity.state.name} | openclaw-ready] "
                f"{self.identity.state.purpose}. "
                "Install claude-agent-sdk for full agent capabilities."
            )
            if gov.decision == "escalate":
                fallback += " This request requires human confirmation."
            self.ale.put(prompt, fallback)
            self.journal.write("openclaw_fallback", {"reason": "sdk_not_available"})
            return to_openclaw_task(fallback, gov.decision)

        # 4. Run Claude Agent SDK with HelloAGI tools
        result_text = ""
        options = ClaudeAgentOptions(
            mcp_servers={"helloagi": _helloagi_mcp_server},
            permission_mode="acceptEdits",
            system_prompt=self._system_prompt(),
            model="claude-opus-4-6",
            max_turns=10,
        )
        async with ClaudeSDKClient(options=options) as client:
            if gov.decision == "escalate":
                await client.query(
                    f"{prompt}\n\n[Note: governance flagged this as medium-risk. "
                    "Confirm with the user before taking any irreversible action.]"
                )
            else:
                await client.query(prompt)

            async for message in client.receive_response():
                if isinstance(message, ResultMessage):
                    result_text = message.result
                    break

        if not result_text:
            result_text = f"[{self.identity.state.name}] Task completed."

        # 5. Cache and journal the result
        self.ale.put(prompt, result_text)
        self.journal.write("openclaw_response", {
            "gov_decision": gov.decision,
            "risk": gov.risk,
            "text_length": len(result_text),
        })

        return to_openclaw_task(result_text, gov.decision)


# ---------------------------------------------------------------------------
# Convenience entry-point
# ---------------------------------------------------------------------------

async def run_openclaw_agent(
    prompt: str,
    settings: RuntimeSettings | None = None,
) -> OpenClawTask:
    """Top-level async entry-point for running the OpenClaw agent."""
    agent = OpenClawAgent(settings=settings)
    return await agent.run(prompt)
