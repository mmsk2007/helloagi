"""System 1 — Expert Mode.

When the router enforces System 1, the agent runs its existing Claude tool-loop
but with three overrides:

  - **Model**: Haiku instead of whatever the keyword router would have picked.
    This is the whole point of Expert Mode — familiar tasks shouldn't pay
    Sonnet/Opus prices.
  - **Prompt addendum**: a short system-prompt note steering the model toward
    the matched skill ("you've done this before — follow the established
    workflow"). The skill index is already injected by the agent, so we don't
    duplicate it; we just elevate its salience.
  - **Turn budget hint**: surfaces the matched skill as the expected path so
    the loop is less tempted to over-explore.

System 1 *does not* introduce a new orchestrator — it's still the existing
``_think_async_claude`` loop with a different model. That keeps the surface
area small and means anything Sonnet learned about reliability, recovery, and
output-guard already applies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agi_runtime.cognition.router import RoutingDecision


# Locked Haiku model id. Centralized so a future swap is one line, not a grep.
EXPERT_MODEL_ID = "claude-haiku-4-5-20251001"


@dataclass(frozen=True)
class ExpertOverrides:
    """Per-call overrides applied while System 1 is active.

    The agent reads these in ``_select_model`` and prompt assembly. Frozen so
    a stale override cannot mutate mid-call.
    """

    model_id: str
    skill_name: str
    skill_relevance: float
    skill_confidence: float
    fingerprint: str
    prompt_addendum: str

    def to_payload(self) -> dict:
        return {
            "model_id": self.model_id,
            "skill_name": self.skill_name,
            "skill_relevance": self.skill_relevance,
            "skill_confidence": self.skill_confidence,
            "fingerprint": self.fingerprint,
        }


def prepare_expert_overrides(
    decision: RoutingDecision,
) -> Optional[ExpertOverrides]:
    """Build an override bundle for an enforced System 1 decision.

    Returns ``None`` when the decision is not an enforced System 1 — callers
    can treat that as "do nothing different".
    """
    if not decision.enforced or decision.system != "system1":
        return None
    if not decision.skill_match_name:
        # Defensive: router shouldn't pick System 1 without a skill, but we
        # never want to enforce a no-skill Haiku path silently.
        return None

    addendum = (
        f"<expert-mode skill=\"{decision.skill_match_name}\" "
        f"relevance=\"{decision.skill_match_relevance:.2f}\" "
        f"confidence=\"{decision.skill_match_confidence:.2f}\">\n"
        f"You've handled this kind of task before. The matched skill "
        f"'{decision.skill_match_name}' is the established workflow — follow "
        f"it directly unless the user's input genuinely conflicts with it. "
        f"Skip exploratory tool calls; pattern is known."
        f"\n</expert-mode>"
    )

    return ExpertOverrides(
        model_id=EXPERT_MODEL_ID,
        skill_name=decision.skill_match_name,
        skill_relevance=float(decision.skill_match_relevance or 0.0),
        skill_confidence=float(decision.skill_match_confidence or 0.0),
        fingerprint=decision.fingerprint,
        prompt_addendum=addendum,
    )


__all__ = ["ExpertOverrides", "prepare_expert_overrides", "EXPERT_MODEL_ID"]
