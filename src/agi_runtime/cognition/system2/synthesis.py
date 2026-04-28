"""Final-decision synthesizer.

Takes the completed debate rounds and the last round's vote tally and
produces:
  - ``final_decision``: the executable instruction the agent will run.
  - ``reasoning_summary``: a short, human-readable trail of how the
    council got there.

Phase 3 ships a deterministic synthesizer that prefers the Synthesizer
agent's last output when present, and falls back to the Planner's last
output otherwise. Phase 5 may upgrade this to a dedicated LLM call that
weaves all positions into prose, but the deterministic version is the
right floor — it always produces *something* even when the LLM path is
unavailable.
"""

from __future__ import annotations

from typing import List, Tuple

from agi_runtime.cognition.trace import DebateRound
from agi_runtime.cognition.system2.agents import (
    PLANNER_ROLE,
    SYNTHESIZER_ROLE,
)
from agi_runtime.cognition.system2.voting import VoteResult


def synthesize(
    *,
    rounds: List[DebateRound],
    final_vote: VoteResult,
    role_lookup: dict,
) -> Tuple[str, str]:
    """Return ``(final_decision, reasoning_summary)``.

    ``role_lookup`` maps agent name → role string so we can find the
    Synthesizer's contribution without re-walking debate rounds.
    """
    if not rounds:
        return ("no_decision", "Council produced no rounds — nothing to decide on.")

    last = rounds[-1]
    decision = ""

    # Prefer the Synthesizer's last output if any synthesizer actually
    # contributed — that's literally their job.
    for name, output in last.agent_outputs.items():
        if role_lookup.get(name) == SYNTHESIZER_ROLE and output:
            decision = output.strip()
            break

    # Fall back to the Planner — the original concrete proposal — if the
    # Synthesizer didn't say anything actionable.
    if not decision:
        for name, output in last.agent_outputs.items():
            if role_lookup.get(name) == PLANNER_ROLE and output:
                decision = output.strip()
                break

    # Last-ditch: any non-empty agent output from the last round.
    if not decision:
        for output in last.agent_outputs.values():
            if output:
                decision = output.strip()
                break

    if not decision:
        decision = "no_decision"

    summary_lines: List[str] = []
    summary_lines.append(
        f"Council ran {len(rounds)} round(s); final vote: yes={final_vote.yes_weight:.2f} "
        f"no={final_vote.no_weight:.2f} → winner={final_vote.winner}."
    )
    if final_vote.consensus:
        summary_lines.append("Consensus reached — no dissent on non-abstain votes.")
    elif final_vote.winner == "tie":
        summary_lines.append("Vote tied; no synthesizer break available.")
    if last.critiques:
        summary_lines.append("Critiques raised: " + " | ".join(last.critiques[:3]))

    return (decision, " ".join(summary_lines))


__all__ = ["synthesize"]
