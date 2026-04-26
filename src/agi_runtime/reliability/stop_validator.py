"""Stop Validator — validates that the agent should stop.

Before the agent returns a final response to the user, this module
checks whether stopping is appropriate: was the goal addressed?
Are there observable artifacts? Does SRG approve?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional

StopDecision = Literal["proceed", "continue", "disclaim"]


@dataclass
class StopCheck:
    """Result of validating whether the agent should stop."""
    decision: StopDecision
    reasons: List[str] = field(default_factory=list)
    disclaimer: str = ""


class StopValidator:
    """Validates that the agent has sufficient reason to stop.

    Lightweight for simple responses (greetings, questions).
    Thorough for multi-step tasks (file operations, code generation).
    """

    # Phrases indicating the agent considers the task complete
    COMPLETION_PHRASES = [
        "task is complete", "task is done", "i've completed",
        "all done", "everything is set", "finished",
        "task has been completed", "successfully completed",
    ]

    def validate(
        self,
        response_text: str,
        tool_calls_made: int = 0,
        tools_used: Optional[List[str]] = None,
        is_multi_step: bool = False,
    ) -> StopCheck:
        """Validate whether stopping is appropriate."""
        if not response_text:
            return StopCheck(decision="proceed", reasons=["empty-response"])

        text_lower = response_text.lower()
        tools_used = tools_used or []

        # Simple responses (greetings, questions, info) — always OK to stop
        if tool_calls_made == 0 and not self._claims_completion(text_lower):
            return StopCheck(decision="proceed", reasons=["informational-response"])

        # Claims completion but no tools used — needs disclaimer
        if self._claims_completion(text_lower) and tool_calls_made == 0:
            return StopCheck(
                decision="disclaim",
                reasons=["completion-claimed-no-tools"],
                disclaimer=(
                    "\n\n*Note: I described what should be done but haven't "
                    "executed the actions yet. Would you like me to proceed "
                    "with the actual implementation?*"
                ),
            )

        # Multi-step task with tools — verify sufficient work was done
        if is_multi_step and tool_calls_made < 2:
            return StopCheck(
                decision="continue",
                reasons=["multi-step-insufficient-progress"],
                disclaimer="This is a multi-step task. More work may be needed.",
            )

        return StopCheck(decision="proceed", reasons=["validated"])

    def _claims_completion(self, text_lower: str) -> bool:
        """Check if the response claims the task is complete."""
        return any(phrase in text_lower for phrase in self.COMPLETION_PHRASES)


__all__ = ["StopValidator", "StopCheck", "StopDecision"]
