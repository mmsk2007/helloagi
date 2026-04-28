"""Recovery Manager — strategy switching on persistent failure.

When the LoopBreaker detects a stuck agent, the Recovery Manager
suggests alternative approaches.  Bounded to prevent meta-loops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RecoveryAction:
    """A suggested recovery action."""
    strategy: str       # "different-tool", "search", "ask-user", "simplify", "abort"
    instruction: str    # Prompt injection text
    attempt: int        # Which recovery attempt this is
    exhausted: bool = False


class RecoveryManager:
    """Manages recovery strategies when the agent is stuck.

    When :py:meth:`suggest` returns ``exhausted=True``, use :py:meth:`exhausted_user_message`
    for the Telegram/UI reply — not ``action.instruction`` (that text is for the model).

    Strategies are tried in order:
    1. Try a different tool for the same task
    2. Search the web for guidance
    3. Simplify the approach
    4. Ask the user for help
    5. Abort with explanation

    Usage::

        recovery = RecoveryManager()
        action = recovery.suggest("same-tool-call", "bash_exec", "file not found")
        if not action.exhausted:
            inject_into_prompt(action.instruction)
    """

    STRATEGIES = [
        (
            "different-tool",
            "Try using a DIFFERENT tool to accomplish this. "
            "For example, if bash_exec failed, try python_exec. "
            "If file_write failed, try file_patch. Think creatively.",
        ),
        (
            "search",
            "Search the web for how to solve this problem. "
            "Use web_search to find relevant documentation or solutions. "
            "Then apply what you learn.",
        ),
        (
            "simplify",
            "Simplify your approach. Break the task into smaller steps. "
            "Try the simplest possible version first, then build up. "
            "Remove any unnecessary complexity.",
        ),
        (
            "ask-user",
            "You've tried multiple approaches without success. "
            "Use ask_user to explain what you've tried and ask for guidance. "
            "Be specific about what's blocking you.",
        ),
        (
            "abort",
            "Multiple recovery strategies have failed. "
            "Explain to the user what you attempted, what failed, and why. "
            "Do NOT claim success — be honest about the limitation.",
        ),
    ]

    EXHAUSTED_USER_MESSAGE = (
        "I stopped because the run kept repeating similar steps without converging "
        "(internal loop protection).\n\n"
        "Try a narrower question (one topic or one time window), or ask me to summarize "
        "what was found so far instead of gathering more."
    )

    @staticmethod
    def exhausted_user_message() -> str:
        """Human-readable text when all recovery strategies have been tried."""
        return RecoveryManager.EXHAUSTED_USER_MESSAGE

    def __init__(self, max_attempts: int = 5):
        self._max_attempts = max_attempts
        self._attempts: dict[str, int] = {}  # session_id → attempt count

    def suggest(
        self,
        loop_type: str = "",
        failed_tool: str = "",
        error_msg: str = "",
        session_id: str = "default",
    ) -> RecoveryAction:
        """Suggest the next recovery strategy."""
        attempt = self._attempts.get(session_id, 0)
        self._attempts[session_id] = attempt + 1

        if attempt >= len(self.STRATEGIES):
            return RecoveryAction(
                strategy="abort",
                instruction=self.STRATEGIES[-1][1],
                attempt=attempt,
                exhausted=True,
            )

        strategy_name, base_instruction = self.STRATEGIES[attempt]

        # Customize instruction based on context
        instruction = base_instruction
        if failed_tool:
            instruction = f"The tool '{failed_tool}' keeps failing. {instruction}"
        if error_msg:
            instruction = f"Error: {error_msg[:150]}. {instruction}"

        return RecoveryAction(
            strategy=strategy_name,
            instruction=instruction,
            attempt=attempt,
            exhausted=False,
        )

    def reset(self, session_id: str = "default") -> None:
        self._attempts.pop(session_id, None)


__all__ = ["RecoveryManager", "RecoveryAction"]
