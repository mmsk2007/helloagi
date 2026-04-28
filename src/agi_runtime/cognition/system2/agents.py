"""Council agents — the roles that argue inside System 2.

Each agent is a thin role wrapper over an LLM call. The council orchestrator
treats every agent as opaque: it gives them the user task, the prior debate
context, and asks for a structured ``AgentTurn`` back.

We define four default roles. They're data — the live roster is configured
in ``helloagi.json`` under ``cognitive_runtime.council.agents``:

  - **Planner**: proposes a concrete plan (steps + tools).
  - **Critic**: attacks the plan; surfaces weak assumptions and missed cases.
  - **Risk Auditor**: scores the plan against SRG-style risk dimensions.
  - **Synthesizer**: breaks ties and writes the final reasoning summary.

Phase 3 ships a stub agent for tests + a real LLM agent that delegates to
the Anthropic SDK. Phase 4 extends with persisted per-agent vote weights;
Phase 5 wraps each in a circuit breaker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ── Role tags. The orchestrator uses these to pick the synthesizer for ───
# tie-breaking and to decide which agent fields the trace surfaces.
PLANNER_ROLE = "planner"
CRITIC_ROLE = "critic"
RISK_AUDITOR_ROLE = "risk_auditor"
SYNTHESIZER_ROLE = "synthesizer"


@dataclass
class AgentTurn:
    """One agent's contribution in one debate round.

    ``vote`` is the agent's structured judgment on the round's proposal.
    The voting alphabet is intentionally small ("yes"/"no"/"abstain") so
    aggregation logic doesn't have to interpret freeform text. ``output``
    carries the freeform reasoning for the trace.
    """

    agent: str = ""
    role: str = ""
    output: str = ""
    vote: str = "abstain"   # "yes" | "no" | "abstain"
    confidence: float = 0.5  # agent's self-reported confidence, 0-1
    suggested_tools: List[str] = field(default_factory=list)
    critique: str = ""

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "role": self.role,
            "output": self.output,
            "vote": self.vote,
            "confidence": self.confidence,
            "suggested_tools": list(self.suggested_tools),
            "critique": self.critique,
        }


@runtime_checkable
class CouncilAgent(Protocol):
    """The protocol every council agent satisfies.

    ``name`` is unique per agent; ``role`` is one of the role tags above.
    ``respond`` is allowed to be sync — the council orchestrator runs each
    agent serially within a single round (debate quality > token speed).
    """

    name: str
    role: str

    def respond(self, *, user_input: str, prior_rounds: List[Any]) -> AgentTurn: ...


@dataclass
class StubCouncilAgent:
    """Canned-response agent for tests and dry-runs.

    Hands back a pre-baked ``AgentTurn`` so we can exercise the debate /
    voting / synthesis layers without an LLM. Real ``LLMCouncilAgent``
    lives next to its prompt templates and is wired in by 3e.
    """

    name: str
    role: str
    canned: AgentTurn

    def respond(self, *, user_input: str, prior_rounds: List[Any]) -> AgentTurn:
        # Return a fresh copy keyed to this agent's name/role so tests can't
        # accidentally mutate the canned source.
        return AgentTurn(
            agent=self.name,
            role=self.role,
            output=self.canned.output,
            vote=self.canned.vote,
            confidence=self.canned.confidence,
            suggested_tools=list(self.canned.suggested_tools),
            critique=self.canned.critique,
        )


# ── Role prompts ─────────────────────────────────────────────────────────
# Used by the LLM-backed agent (3e). Defined here so every place that
# instantiates a council agent reads the same prompt source-of-truth.

PLANNER_PROMPT = (
    "You are the Planner on a small reasoning council. Read the user task "
    "and propose ONE concrete plan: a numbered list of steps and the "
    "specific tools each step would use. Be honest about uncertainty. "
    "Then vote 'yes' on your own plan with a confidence score 0-1. Output "
    "JSON with keys: plan, suggested_tools, vote, confidence, output."
)

CRITIC_PROMPT = (
    "You are the Critic. Your job is to attack the Planner's proposal and "
    "find what's wrong with it: missed cases, brittle assumptions, "
    "tool/permission gaps, or a misread of what the user actually wants. "
    "If the plan is solid, say so. Vote 'yes' to endorse, 'no' to block, "
    "'abstain' if undecided. Output JSON with keys: critique, vote, "
    "confidence, output."
)

RISK_AUDITOR_PROMPT = (
    "You are the Risk Auditor. Read the proposed plan and score it on: "
    "blast radius, reversibility, governance compliance, and credential/PII "
    "exposure. If the plan crosses a risk threshold, vote 'no' and explain. "
    "Output JSON with keys: risk_summary, vote, confidence, output."
)

SYNTHESIZER_PROMPT = (
    "You are the Synthesizer. You see all council members' positions and "
    "the votes. Your job: write the final decision the agent will execute, "
    "plus a short reasoning summary explaining how the council got there. "
    "If votes tied, you decide. Output JSON with keys: final_decision, "
    "reasoning_summary, vote (always 'yes'), confidence."
)


__all__ = [
    "PLANNER_ROLE",
    "CRITIC_ROLE",
    "RISK_AUDITOR_ROLE",
    "SYNTHESIZER_ROLE",
    "AgentTurn",
    "CouncilAgent",
    "StubCouncilAgent",
    "PLANNER_PROMPT",
    "CRITIC_PROMPT",
    "RISK_AUDITOR_PROMPT",
    "SYNTHESIZER_PROMPT",
]
