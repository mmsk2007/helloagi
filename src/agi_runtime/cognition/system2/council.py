"""AgentCouncil — orchestrator that ties debate, voting, and synthesis
together and produces a persistable ``CouncilTrace``.

Phase 3 scope: deliberate over a user task, return the final decision plus
the trace. The agent loop consumes the decision; ``ThinkingTraceStore``
persists the trace; Phase 4 watches outcomes to crystallize skills.

This class is deliberately I/O-light. The trace store and the LLM client
are passed in (or absent) — the council itself is just orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agi_runtime.cognition.trace import (
    CouncilTrace,
    DebateRound,
    ThinkingTraceStore,
)
from agi_runtime.cognition.system2.agents import CouncilAgent
from agi_runtime.cognition.system2.debate import run_debate
from agi_runtime.cognition.system2.synthesis import synthesize
from agi_runtime.cognition.system2.voting import (
    VoteResult,
    VoteWeights,
    aggregate_votes,
)


@dataclass
class CouncilOutcome:
    """What the agent loop gets back from a council deliberation."""

    final_decision: str
    reasoning_summary: str
    trace: CouncilTrace
    vote: VoteResult


class AgentCouncil:
    """Bounded debate orchestrator.

    Compose with:
        council = AgentCouncil(
            agents=[planner, critic, risk_auditor, synthesizer],
            weights=VoteWeights("memory/cognition/agent_weights.json"),
            trace_store=ThinkingTraceStore("memory/cognition/traces"),
            max_rounds=2,
        )
        outcome = council.deliberate(user_input="...", fingerprint="...")

    All collaborators are optional so test code can pass nothing and still
    get a working council over stubs.
    """

    def __init__(
        self,
        *,
        agents: List[CouncilAgent],
        weights: Optional[VoteWeights] = None,
        trace_store: Optional[ThinkingTraceStore] = None,
        max_rounds: int = 2,
        early_exit_on_consensus: bool = True,
        journal: Any = None,
        breaker: Any = None,
    ):
        if not agents:
            raise ValueError("AgentCouncil requires at least one agent")
        self.agents = list(agents)
        self.weights = weights
        self.trace_store = trace_store
        self.max_rounds = max(1, int(max_rounds))
        self.early_exit_on_consensus = bool(early_exit_on_consensus)
        self.journal = journal
        # Optional per-agent breaker. The council uses a stricter threshold
        # (3 failures, 30s cooldown) than the global tool breaker — a
        # mis-prompted agent that returns no_json should be sidelined fast,
        # then probed back in shortly so a transient hiccup doesn't
        # permanently silence a voice.
        if breaker is None:
            from agi_runtime.robustness.circuit_breaker import CircuitBreaker
            breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
        self.breaker = breaker

    def deliberate(
        self,
        *,
        user_input: str,
        fingerprint: str = "",
        srg_decision: Optional[Dict[str, Any]] = None,
    ) -> CouncilOutcome:
        rounds: List[DebateRound] = run_debate(
            user_input=user_input,
            agents=self.agents,
            weights=self.weights,
            max_rounds=self.max_rounds,
            early_exit_on_consensus=self.early_exit_on_consensus,
            breaker=self.breaker,
        )

        # Re-tally the last round's votes. ``run_debate`` already did this
        # internally, but we need the structured ``VoteResult`` here.
        final_vote: VoteResult
        if rounds:
            last = rounds[-1]
            from agi_runtime.cognition.system2.agents import AgentTurn
            replay = [
                AgentTurn(
                    agent=name,
                    role=self._role_of(name),
                    output=last.agent_outputs.get(name, ""),
                    vote=last.votes.get(name, "abstain"),
                    confidence=0.7,  # confidence isn't stored in the round; assume default
                )
                for name in last.agent_outputs.keys()
            ]
            final_vote = aggregate_votes(replay, self.weights)
        else:
            final_vote = VoteResult(
                winner="tie", yes_weight=0.0, no_weight=0.0, abstain_weight=0.0
            )

        role_lookup = {a.name: a.role for a in self.agents}
        decision, summary = synthesize(
            rounds=rounds, final_vote=final_vote, role_lookup=role_lookup
        )

        trace = CouncilTrace(
            fingerprint=fingerprint,
            user_input=user_input,
            rounds=rounds,
            final_decision=decision,
            reasoning_summary=summary,
            srg_decision=dict(srg_decision or {}),
            agent_weights_at_run={
                a.name: (self.weights.get(a.name) if self.weights else 1.0)
                for a in self.agents
            },
        )

        if self.trace_store is not None:
            try:
                self.trace_store.write(trace)
            except Exception:
                pass

        if self.journal is not None and hasattr(self.journal, "write"):
            try:
                self.journal.write("council.deliberated", {
                    "trace_id": trace.trace_id,
                    "fingerprint": fingerprint,
                    "rounds": len(rounds),
                    "winner": final_vote.winner,
                    "consensus": final_vote.consensus,
                })
            except Exception:
                pass

        return CouncilOutcome(
            final_decision=decision,
            reasoning_summary=summary,
            trace=trace,
            vote=final_vote,
        )

    def _role_of(self, agent_name: str) -> str:
        for a in self.agents:
            if a.name == agent_name:
                return a.role
        return ""


__all__ = ["AgentCouncil", "CouncilOutcome"]
