"""Loop Breaker — detects and breaks repetitive agent behavior.

Monitors recent tool calls and responses per session.  When the agent
repeats the same failed strategy, the breaker injects a recovery
instruction to force a different approach.
"""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple


@dataclass
class LoopSignal:
    """Signal that a loop has been detected."""
    detected: bool = False
    loop_type: str = ""  # "same-tool-call", "same-error", "same-response"
    repetition_count: int = 0
    recovery_instruction: str = ""


@dataclass
class _CallRecord:
    """One tool call for loop tracking."""
    tool: str
    args_hash: str
    error: str = ""
    response_hash: str = ""


# Read-only web tools: many legitimate calls in a row (e.g. news research) are not a "stuck" loop.
_RESEARCH_SAME_NAME_TOOLS = frozenset({"web_search", "web_fetch"})
_RESEARCH_SAME_NAME_MIN_REPEATS = 16


class LoopBreaker:
    """Detects repetitive agent behavior and suggests recovery.

    Tracks the last N tool calls per session.  Detection patterns:
    1. Same tool + same args called >= threshold times
    2. Same error message repeated >= threshold times
    3. Same response hash repeated >= threshold times

    Usage::

        breaker = LoopBreaker()
        # Record each tool call
        breaker.record_call("bash_exec", {"command": "ls"}, error="")
        # Check before next LLM call
        signal = breaker.check()
        if signal.detected:
            inject_into_prompt(signal.recovery_instruction)
    """

    def __init__(
        self,
        *,
        window_size: int = 20,
        repetition_threshold: int = 3,
        same_name_threshold: int = 5,
    ):
        self._window_size = window_size
        self._threshold = repetition_threshold
        # Looser pattern: same tool *name* (regardless of args). Catches the
        # case where the model reformulates the query each retry and the
        # args-hash check misses it — e.g. five web_searches with slightly
        # different phrasings all asking the same thing.
        self._same_name_threshold = same_name_threshold
        # Per-session tracking
        self._sessions: Dict[str, Deque[_CallRecord]] = {}
        self._recovery_count: Dict[str, int] = {}  # Track recovery attempts
        self._max_recoveries = 5  # Prevent meta-loops

    def record_call(
        self,
        tool: str,
        args: dict | str = "",
        error: str = "",
        response: str = "",
        session_id: str = "default",
    ) -> None:
        """Record a tool call for loop detection."""
        if session_id not in self._sessions:
            self._sessions[session_id] = deque(maxlen=self._window_size)
        self._sessions[session_id].append(_CallRecord(
            tool=tool,
            args_hash=_hash(str(args)),
            error=error[:200] if error else "",
            response_hash=_hash(response[:500]) if response else "",
        ))

    def check(self, session_id: str = "default") -> LoopSignal:
        """Check for loop patterns in recent calls."""
        history = self._sessions.get(session_id)
        if not history or len(history) < self._threshold:
            return LoopSignal()

        # Check if we've exhausted recovery attempts
        if self._recovery_count.get(session_id, 0) >= self._max_recoveries:
            return LoopSignal(
                detected=True,
                loop_type="recovery-exhausted",
                repetition_count=self._recovery_count[session_id],
                recovery_instruction=(
                    "IMPORTANT: Multiple recovery attempts have failed. "
                    "Stop trying this approach entirely. Ask the user for "
                    "guidance with ask_user, or explain what's blocking you."
                ),
            )

        recent = list(history)

        # Pattern 1: Same tool + same args
        signal = self._check_same_call(recent)
        if signal.detected:
            self._recovery_count[session_id] = self._recovery_count.get(session_id, 0) + 1
            return signal

        # Pattern 2: Same error repeated
        signal = self._check_same_error(recent)
        if signal.detected:
            self._recovery_count[session_id] = self._recovery_count.get(session_id, 0) + 1
            return signal

        # Pattern 3: Same response pattern
        signal = self._check_same_response(recent)
        if signal.detected:
            self._recovery_count[session_id] = self._recovery_count.get(session_id, 0) + 1
            return signal

        # Pattern 4: Same tool *name* repeated regardless of args.
        signal = self._check_same_tool_name(recent)
        if signal.detected:
            self._recovery_count[session_id] = self._recovery_count.get(session_id, 0) + 1
            return signal

        return LoopSignal()

    def reset(self, session_id: str = "default") -> None:
        """Reset tracking for a session (e.g., on new task)."""
        self._sessions.pop(session_id, None)
        self._recovery_count.pop(session_id, None)

    def _check_same_call(self, recent: List[_CallRecord]) -> LoopSignal:
        """Detect same tool+args repeated."""
        if len(recent) < self._threshold:
            return LoopSignal()
        tail = recent[-self._threshold:]
        if all(r.tool == tail[0].tool and r.args_hash == tail[0].args_hash for r in tail):
            return LoopSignal(
                detected=True,
                loop_type="same-tool-call",
                repetition_count=self._threshold,
                recovery_instruction=(
                    f"LOOP DETECTED: You've called '{tail[0].tool}' with the same "
                    f"arguments {self._threshold} times. This approach isn't working. "
                    f"Try a DIFFERENT tool or a DIFFERENT approach entirely. "
                    f"If you're stuck, use 'web_search' to find guidance or "
                    f"'ask_user' to request clarification."
                ),
            )
        return LoopSignal()

    def _check_same_error(self, recent: List[_CallRecord]) -> LoopSignal:
        """Detect same error repeated."""
        errors = [r.error for r in recent[-self._threshold:] if r.error]
        if len(errors) >= self._threshold and len(set(errors)) == 1:
            return LoopSignal(
                detected=True,
                loop_type="same-error",
                repetition_count=len(errors),
                recovery_instruction=(
                    f"LOOP DETECTED: The same error has occurred {len(errors)} times: "
                    f"'{errors[0][:100]}'. Stop repeating this approach. "
                    f"Analyze the error, try a completely different strategy, "
                    f"or ask the user for help."
                ),
            )
        return LoopSignal()

    def _check_same_response(self, recent: List[_CallRecord]) -> LoopSignal:
        """Detect same response hash repeated."""
        hashes = [r.response_hash for r in recent[-self._threshold:] if r.response_hash]
        if len(hashes) >= self._threshold and len(set(hashes)) == 1:
            return LoopSignal(
                detected=True,
                loop_type="same-response",
                repetition_count=len(hashes),
                recovery_instruction=(
                    f"LOOP DETECTED: You've produced the same response pattern "
                    f"{len(hashes)} times. You appear to be stuck in a loop. "
                    f"Try a fundamentally different approach to this task."
                ),
            )
        return LoopSignal()

    def _check_same_tool_name(self, recent: List[_CallRecord]) -> LoopSignal:
        """Detect repeated calls to the same tool *name*, ignoring args.

        Catches the case where the model varies its query each retry — e.g.
        five web_searches with slightly different phrasings — which sidesteps
        the args-hash check in :py:meth:`_check_same_call`.

        ``web_search`` / ``web_fetch`` get a higher bar: multi-query research is normal.
        """
        if not recent:
            return LoopSignal()
        tool = recent[-1].tool
        threshold = self._same_name_threshold
        if tool in _RESEARCH_SAME_NAME_TOOLS:
            threshold = max(threshold, _RESEARCH_SAME_NAME_MIN_REPEATS)
        if len(recent) < threshold:
            return LoopSignal()
        tail = recent[-threshold:]
        if all(r.tool == tail[0].tool for r in tail):
            return LoopSignal(
                detected=True,
                loop_type="same-tool-name",
                repetition_count=len(tail),
                recovery_instruction=(
                    f"LOOP DETECTED: You've called '{tail[0].tool}' "
                    f"{len(tail)} times in a row with varying arguments and "
                    "still aren't converging on an answer. Stop calling "
                    f"'{tail[0].tool}'. Either summarise what you've already "
                    "learned and answer the user with that, or ask the user "
                    "to clarify (use 'ask_user' if helpful) — don't keep "
                    "issuing more queries."
                ),
            )
        return LoopSignal()


def _hash(s: str) -> str:
    """Fast hash for comparison (not crypto)."""
    return hashlib.md5(s.encode(), usedforsecurity=False).hexdigest()[:16]


__all__ = ["LoopBreaker", "LoopSignal"]
