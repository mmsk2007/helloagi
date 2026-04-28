"""Bounded debate runner.

Each round, every agent gets to respond given the user task and the prior
rounds. Then the round's votes get aggregated. If the council reaches
consensus (everyone who voted agreed), we early-exit — no point burning
tokens on a settled question. If they're split, the next round runs with
the dissent visible to all agents.

Bounded by ``max_rounds`` from posture/config so a hostile loop can't
spin the council forever.

Phase 5 hardening: an optional ``CircuitBreaker`` isolates flaky agents.
If an agent's ``respond`` raises or returns an error-shaped abstain (a
client_error / no_json critique), we count that as a failure. After the
breaker opens, that agent is short-circuited — its turn is replaced with
a synthetic abstain so the rest of the council can still debate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from agi_runtime.cognition.trace import DebateRound
from agi_runtime.cognition.system2.agents import AgentTurn, CouncilAgent
from agi_runtime.cognition.system2.voting import (
    VoteResult,
    VoteWeights,
    aggregate_votes,
)


# Critique substrings produced by LLMCouncilAgent on internal errors.
# Treat these as breaker-counted failures even though the agent didn't raise.
_ERROR_CRITIQUE_TAGS = ("client_error", "no_json", "parse_error")


def _is_error_turn(turn: AgentTurn) -> bool:
    crit = (turn.critique or "").lower()
    return any(tag in crit for tag in _ERROR_CRITIQUE_TAGS)


def _short_circuited_turn(agent: CouncilAgent) -> AgentTurn:
    return AgentTurn(
        agent=getattr(agent, "name", ""),
        role=getattr(agent, "role", ""),
        output="",
        vote="abstain",
        confidence=0.0,
        critique="circuit_open",
    )


def _safe_respond(
    agent: CouncilAgent,
    *,
    user_input: str,
    prior_rounds: List[DebateRound],
    breaker: Optional[Any],
) -> AgentTurn:
    """Run one agent turn through the breaker. Never raises."""
    name = getattr(agent, "name", "") or "agent"
    if breaker is not None and not breaker.can_execute(name):
        return _short_circuited_turn(agent)
    try:
        turn = agent.respond(user_input=user_input, prior_rounds=prior_rounds)
    except Exception as exc:
        if breaker is not None:
            breaker.record_failure(name)
        return AgentTurn(
            agent=name,
            role=getattr(agent, "role", ""),
            vote="abstain",
            confidence=0.0,
            critique=f"client_error: {type(exc).__name__}",
        )
    if breaker is not None:
        if _is_error_turn(turn):
            breaker.record_failure(name)
        else:
            breaker.record_success(name)
    return turn


@dataclass
class RoundContext:
    """Inputs every agent sees on every round."""

    user_input: str
    prior_rounds: List[DebateRound]


def run_debate(
    *,
    user_input: str,
    agents: List[CouncilAgent],
    weights: Optional[VoteWeights] = None,
    max_rounds: int = 2,
    early_exit_on_consensus: bool = True,
    breaker: Optional[Any] = None,
) -> List[DebateRound]:
    """Drive ``max_rounds`` of round-robin debate.

    Returns the list of completed ``DebateRound``s in order. Each round
    persists each agent's freeform output, the critiques surfaced, the
    structured votes, and a one-line note about the aggregate.
    """
    if not agents:
        return []
    rounds: List[DebateRound] = []
    bound = max(1, int(max_rounds))

    for round_index in range(bound):
        context = RoundContext(user_input=user_input, prior_rounds=list(rounds))
        agent_outputs = {}
        critiques: List[str] = []
        votes = {}
        turns: List[AgentTurn] = []

        for agent in agents:
            turn = _safe_respond(
                agent,
                user_input=user_input,
                prior_rounds=context.prior_rounds,
                breaker=breaker,
            )
            # Defensive — make sure the turn carries the agent's identity
            # even if a stub forgot to set them.
            turn.agent = turn.agent or getattr(agent, "name", "")
            turn.role = turn.role or getattr(agent, "role", "")
            turns.append(turn)
            agent_outputs[turn.agent] = turn.output
            votes[turn.agent] = turn.vote
            if turn.critique:
                critiques.append(f"{turn.agent}: {turn.critique}")

        result: VoteResult = aggregate_votes(turns, weights)
        note = (
            f"winner={result.winner}, "
            f"yes={result.yes_weight:.2f}, "
            f"no={result.no_weight:.2f}, "
            f"consensus={result.consensus}"
        )

        rounds.append(DebateRound(
            round_index=round_index,
            agent_outputs=agent_outputs,
            critiques=critiques,
            votes=votes,
            notes=note,
        ))

        if early_exit_on_consensus and result.consensus:
            break

    return rounds


__all__ = ["RoundContext", "run_debate"]
