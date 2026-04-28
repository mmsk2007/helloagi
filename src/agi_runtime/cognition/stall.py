"""Stall detector — mid-loop guard that catches the "40 turns without an
answer" failure mode before it burns the whole budget.

The classic case: the agent fires off bash/python calls, none of them
actually move toward the goal, and it keeps spinning because no rule says
"stop and rethink." LoopBreaker catches *exact* repetition, but the agent
that spends 40 turns on follower-count without ever opening the browser
isn't repeating — each tool call is different, just useless.

This module looks for a softer pattern: ``N consecutive turns with tool
calls but no narration text``. That's the LLM running on autopilot. When
it crosses a threshold, the agent loop injects a warning asking the model
to summarize what it tried and consider switching approach.

Plain dataclass + pure-function design keeps this trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass


# Defaults. Configurable via ``cognitive_runtime.stall`` in helloagi.json.
_DEFAULT_SILENT_TURN_BUDGET = 4    # 4 silent turns in a row triggers the warning
_DEFAULT_WARM_UP_TOOL_CALLS = 5    # ignore stalls for the first 5 tool calls
_DEFAULT_TEXT_THRESHOLD = 40       # under N chars of text counts as "silent"


@dataclass
class StallSignal:
    detected: bool = False
    consecutive_silent_turns: int = 0
    total_tool_calls: int = 0
    reason: str = ""


class StallDetector:
    """Counts silent-tool-only turns and emits a one-shot stall signal.

    Usage inside the agent loop, once per LLM turn:

        det.observe(text_chars=len("\n".join(text_parts)),
                    tool_call_count=len(tool_calls))
        sig = det.check()
        if sig.detected:
            # Inject the warning, then `det.acknowledge()` so we don't
            # re-fire on the very next turn.
            ...

    The detector is *advisory* — the agent loop decides whether to inject
    a reminder, escalate to System 2, or keep going. We don't terminate
    the loop ourselves; that's the existing soft-timeout / max_turns'
    job.
    """

    def __init__(
        self,
        *,
        silent_turn_budget: int = _DEFAULT_SILENT_TURN_BUDGET,
        warm_up_tool_calls: int = _DEFAULT_WARM_UP_TOOL_CALLS,
        text_threshold: int = _DEFAULT_TEXT_THRESHOLD,
    ):
        self.silent_turn_budget = max(1, int(silent_turn_budget))
        self.warm_up_tool_calls = max(0, int(warm_up_tool_calls))
        self.text_threshold = max(0, int(text_threshold))
        self._silent_streak = 0
        self._total_tool_calls = 0
        self._already_fired = False

    def observe(self, *, text_chars: int, tool_call_count: int) -> None:
        self._total_tool_calls += int(tool_call_count or 0)
        is_silent_tool_turn = (
            int(tool_call_count or 0) > 0
            and int(text_chars or 0) < self.text_threshold
        )
        if is_silent_tool_turn:
            self._silent_streak += 1
        else:
            # Any narrative text (or a no-tool turn) resets the streak —
            # the agent is back to thinking aloud.
            self._silent_streak = 0
            self._already_fired = False

    def check(self) -> StallSignal:
        if self._already_fired:
            return StallSignal()
        if self._total_tool_calls < self.warm_up_tool_calls:
            return StallSignal(
                consecutive_silent_turns=self._silent_streak,
                total_tool_calls=self._total_tool_calls,
            )
        if self._silent_streak < self.silent_turn_budget:
            return StallSignal(
                consecutive_silent_turns=self._silent_streak,
                total_tool_calls=self._total_tool_calls,
            )
        return StallSignal(
            detected=True,
            consecutive_silent_turns=self._silent_streak,
            total_tool_calls=self._total_tool_calls,
            reason=(
                f"{self._silent_streak} consecutive turns with tool calls "
                f"but no narration text after {self._total_tool_calls} "
                f"total tool calls — likely floundering."
            ),
        )

    def acknowledge(self) -> None:
        """Caller has handled the signal; don't re-fire until streak resets."""
        self._already_fired = True


_REMINDER_TEMPLATE = (
    "<turn-budget-warning>\n"
    "You have made {tool_calls} tool calls across {silent_turns} consecutive "
    "turns without producing any answer text. That's a stall. Stop and do "
    "this in your next turn — no tool calls:\n"
    "  1. Summarize what each tool call returned and what it told you.\n"
    "  2. Restate the user's actual goal in one sentence.\n"
    "  3. Decide: are the tools you've been using the right ones? If a "
    "different tool family (e.g., the browser instead of bash, or a search "
    "tool instead of file ops) would more directly answer the goal, switch.\n"
    "  4. If you genuinely cannot make progress with the available tools, "
    "say so plainly to the user instead of trying more.\n"
    "</turn-budget-warning>"
)


def build_reminder(signal: StallSignal) -> str:
    return _REMINDER_TEMPLATE.format(
        tool_calls=signal.total_tool_calls,
        silent_turns=signal.consecutive_silent_turns,
    )


def detector_from_config(cfg: dict) -> StallDetector:
    """Build a StallDetector from a ``cognitive_runtime.stall`` config block."""
    sub = (cfg or {}).get("stall") if isinstance(cfg, dict) else None
    sub = sub or {}
    return StallDetector(
        silent_turn_budget=int(sub.get("silent_turn_budget", _DEFAULT_SILENT_TURN_BUDGET)),
        warm_up_tool_calls=int(sub.get("warm_up_tool_calls", _DEFAULT_WARM_UP_TOOL_CALLS)),
        text_threshold=int(sub.get("text_threshold", _DEFAULT_TEXT_THRESHOLD)),
    )


__all__ = [
    "StallDetector",
    "StallSignal",
    "build_reminder",
    "detector_from_config",
]
