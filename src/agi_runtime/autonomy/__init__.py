"""Autonomy primitives.

This package provides Hello AGI's autonomous-execution surface:

- :class:`AutonomousLoop` (in ``agi_runtime.autonomy.loop``) — the original
  fixed-step iterator. Kept for backward compatibility.
- :class:`TriLoop` (in ``agi_runtime.autonomy.tri_loop``) — the SRG-governed
  Plan → Execute → Verify → Replan loop. New autonomous runs should use it.

Only lightweight symbols are eagerly re-exported here. ``AutonomousLoop``
drags in the full agent (and its LLM-provider deps) through its import
chain; we leave it behind a lazy import so ``from agi_runtime.autonomy
import TriLoop`` stays fast and dependency-free.
"""

from agi_runtime.autonomy.tri_loop import (
    IterationTrace,
    StepTrace,
    TriLoop,
    TriLoopResult,
    TriLoopStatus,
)

__all__ = [
    "TriLoop",
    "TriLoopResult",
    "TriLoopStatus",
    "IterationTrace",
    "StepTrace",
    "AutonomousLoop",  # lazy; see __getattr__ below
]


def __getattr__(name: str):
    """PEP 562 lazy attribute access — only imports AutonomousLoop on demand.

    This keeps ``from agi_runtime.autonomy import TriLoop`` decoupled from
    the heavier core-agent import chain, while still letting existing
    callers do ``from agi_runtime.autonomy import AutonomousLoop``.
    """
    if name == "AutonomousLoop":
        from agi_runtime.autonomy.loop import AutonomousLoop
        return AutonomousLoop
    raise AttributeError(f"module 'agi_runtime.autonomy' has no attribute {name!r}")
