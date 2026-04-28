"""Vote aggregation with per-agent weights.

The council doesn't take a flat majority — agents who've been right in the
past have heavier votes than ones who've been wrong. Phase 4 will mutate
weights based on outcomes (a Critic that flagged what turned out to be a
real bug gets boosted; an agent that voted yes on a plan that failed gets
trimmed). Phase 3 just ships the math + persistence so weights have a
home.

Storage: ``memory/cognition/agent_weights.json`` — a flat
``{agent_name: weight}`` map. Missing entries default to 1.0. Weights are
clamped to a sane range so a runaway feedback loop can't send one agent's
vote to zero or infinity.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agi_runtime.cognition.system2.agents import AgentTurn, SYNTHESIZER_ROLE


_MIN_WEIGHT = 0.1
_MAX_WEIGHT = 3.0
_DEFAULT_WEIGHT = 1.0


class VoteWeights:
    """Persistable per-agent vote weights.

    Use ``get(name)`` to read; ``set(name, value)`` to write. The store is
    write-through — mutations are saved immediately so a crash doesn't
    lose calibrated weights.
    """

    def __init__(self, path: str = "memory/cognition/agent_weights.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._weights: Dict[str, float] = self._load()

    def _load(self) -> Dict[str, float]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    str(k): _clamp(float(v))
                    for k, v in data.items()
                    if isinstance(v, (int, float))
                }
        except Exception:
            pass
        return {}

    def _save(self) -> None:
        try:
            self.path.write_text(
                json.dumps(self._weights, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def get(self, name: str) -> float:
        return self._weights.get(name, _DEFAULT_WEIGHT)

    def set(self, name: str, value: float) -> None:
        self._weights[name] = _clamp(float(value))
        self._save()

    def adjust(self, name: str, delta: float) -> float:
        new = _clamp(self.get(name) + float(delta))
        self._weights[name] = new
        self._save()
        return new

    def snapshot(self) -> Dict[str, float]:
        return dict(self._weights)


def _clamp(v: float) -> float:
    return max(_MIN_WEIGHT, min(_MAX_WEIGHT, float(v)))


@dataclass
class VoteResult:
    """Aggregated outcome of one round of votes."""

    winner: str        # "yes" | "no" | "tie"
    yes_weight: float
    no_weight: float
    abstain_weight: float
    tally: Dict[str, float] = field(default_factory=dict)  # agent_name -> weight applied
    consensus: bool = False  # True iff all non-abstain votes agreed

    def to_dict(self) -> dict:
        return {
            "winner": self.winner,
            "yes_weight": self.yes_weight,
            "no_weight": self.no_weight,
            "abstain_weight": self.abstain_weight,
            "tally": dict(self.tally),
            "consensus": self.consensus,
        }


def aggregate_votes(
    turns: List[AgentTurn],
    weights: Optional[VoteWeights] = None,
    *,
    tie_breaker_role: str = SYNTHESIZER_ROLE,
) -> VoteResult:
    """Combine the round's AgentTurns into a single weighted decision.

    A tie at the weighted level is resolved by the agent whose ``role``
    matches ``tie_breaker_role`` (default: Synthesizer). If no synthesizer
    voted, the tie is recorded as ``winner="tie"`` and left for the caller
    to handle.
    """
    yes_w = 0.0
    no_w = 0.0
    abstain_w = 0.0
    tally: Dict[str, float] = {}
    nonabstain_votes: set = set()

    for turn in turns:
        w = weights.get(turn.agent) if weights is not None else _DEFAULT_WEIGHT
        # Confidence weighting: an agent at 0.9 confidence gets full vote
        # weight; one at 0.4 gets ~half. Floors at a small minimum so a
        # confident-but-wrong-history agent still gets a voice.
        conf = max(0.2, min(1.0, float(turn.confidence or 0.5)))
        applied = w * conf
        tally[turn.agent] = applied
        if turn.vote == "yes":
            yes_w += applied
            nonabstain_votes.add("yes")
        elif turn.vote == "no":
            no_w += applied
            nonabstain_votes.add("no")
        else:
            abstain_w += applied

    if yes_w > no_w:
        winner = "yes"
    elif no_w > yes_w:
        winner = "no"
    else:
        # Tie — let the synthesizer break it.
        synth_vote = next(
            (t.vote for t in turns if t.role == tie_breaker_role and t.vote in ("yes", "no")),
            None,
        )
        winner = synth_vote if synth_vote else "tie"

    consensus = len(nonabstain_votes) == 1
    return VoteResult(
        winner=winner,
        yes_weight=yes_w,
        no_weight=no_w,
        abstain_weight=abstain_w,
        tally=tally,
        consensus=consensus,
    )


# ── Outcome-driven weight nudges ─────────────────────────────────────────


# Default deltas. Conservative on purpose — one pass/fail moves the needle a
# little; a streak moves it a lot. Anti-runaway: clamping in VoteWeights
# bounds final values to [0.1, 3.0] so a chronically-wrong agent stays in the
# room (with a quiet voice) and a chronically-right one can't drown out the
# others.
_NUDGE_BOOST = 0.06
_NUDGE_TRIM = -0.10


def nudge_weights_from_outcome(
    *,
    weights: "VoteWeights",
    last_round_votes: Dict[str, str],
    success: bool,
    boost: float = _NUDGE_BOOST,
    trim: float = _NUDGE_TRIM,
) -> Dict[str, float]:
    """Adjust per-agent weights based on whether their last vote matched
    the verified outcome.

    Logic:
      - On a successful run, agents that voted "yes" get a small boost
        (they backed a winner). "no" voters get a small trim (they
        dissented from a good plan, but only mildly — sometimes the
        critic is right to dissent and the plan still works).
      - On a failed run, "yes" voters get trimmed (they greenlit a bad
        plan) and "no" voters get boosted (their dissent was prophetic).
      - Abstainers neither help nor hurt — no nudge.

    Returns the updated weight snapshot keyed by agent name.
    """
    if weights is None:
        return {}
    updated: Dict[str, float] = {}
    for agent, vote in (last_round_votes or {}).items():
        if vote == "yes":
            delta = boost if success else trim
        elif vote == "no":
            delta = trim if success else boost
        else:
            delta = 0.0
        if delta == 0.0:
            updated[agent] = weights.get(agent)
            continue
        updated[agent] = weights.adjust(agent, delta)
    return updated


__all__ = [
    "VoteWeights",
    "VoteResult",
    "aggregate_votes",
    "nudge_weights_from_outcome",
]
