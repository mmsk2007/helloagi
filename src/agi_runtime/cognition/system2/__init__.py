"""System 2 — Agent Council package.

System 2 is the slow, deeper-thinking path for novel or risky tasks. It runs
a small council of role-specialized agents (Planner, Critic, Risk Auditor,
Synthesizer) in a bounded debate, aggregates their votes with per-agent
weights, synthesizes a single final decision, and stores the full trace
for later replay or skill crystallization.

Public surface:
    AgentTurn           — what one agent contributed in one round
    CouncilAgent        — protocol every council agent satisfies
    StubCouncilAgent    — canned-response agent for tests / dry-run
    VoteResult          — winning position + per-agent tally
    aggregate_votes     — weighted-vote aggregator
    run_debate          — bounded round-robin debate loop
    synthesize          — final decision + reasoning summary
    AgentCouncil        — orchestrator that ties the four together
"""

from agi_runtime.cognition.system2.agents import (
    AgentTurn,
    CouncilAgent,
    StubCouncilAgent,
    PLANNER_ROLE,
    CRITIC_ROLE,
    RISK_AUDITOR_ROLE,
    SYNTHESIZER_ROLE,
)
from agi_runtime.cognition.system2.voting import (
    VoteResult,
    VoteWeights,
    aggregate_votes,
)
from agi_runtime.cognition.system2.debate import (
    RoundContext,
    run_debate,
)
from agi_runtime.cognition.system2.synthesis import synthesize
from agi_runtime.cognition.system2.council import AgentCouncil, CouncilOutcome
from agi_runtime.cognition.system2.llm_agent import (
    LLMCouncilAgent,
    make_default_roster,
    DEFAULT_COUNCIL_MODEL,
    SYNTHESIZER_DEFAULT_MODEL,
)

__all__ = [
    "AgentTurn",
    "CouncilAgent",
    "StubCouncilAgent",
    "PLANNER_ROLE",
    "CRITIC_ROLE",
    "RISK_AUDITOR_ROLE",
    "SYNTHESIZER_ROLE",
    "VoteResult",
    "VoteWeights",
    "aggregate_votes",
    "RoundContext",
    "run_debate",
    "synthesize",
    "AgentCouncil",
    "CouncilOutcome",
    "LLMCouncilAgent",
    "make_default_roster",
    "DEFAULT_COUNCIL_MODEL",
    "SYNTHESIZER_DEFAULT_MODEL",
]
