"""Governance surface — SRG and its peers.

Hello AGI's moat is governed autonomy. This package is the enforcement
surface: the deterministic, prompt-injection-immune Python layer that
every autonomous action flows through.

Public surface:

- :class:`SRGGovernor` — input-side gate: evaluates user text and
  individual tool-call intents before execution.
- :class:`OutputGuard` — output-side gate: scans tool outputs and agent
  text for secret leakage and phantom actions before emission.
- :class:`PostureEngine` — derives a runtime :class:`Posture`
  (conservative / balanced / aggressive) per autonomous goal; posture
  scales thresholds, replan budget, and failure tolerance.

Both gates are pure Python and deterministic by design. The whole point
of the moat is that *no prompt can override Python*.
"""

from agi_runtime.governance.output_guard import (
    OutputGuard,
    OutputGuardResult,
    PHANTOM_ACTION_PATTERNS,
)
from agi_runtime.governance.posture import (
    AGGRESSIVE,
    BALANCED,
    CONSERVATIVE,
    Posture,
    PostureEngine,
    PostureName,
)
from agi_runtime.governance.srg import (
    Decision,
    GovernanceResult,
    Policy,
    SRGGovernor,
)

__all__ = [
    # SRG
    "SRGGovernor",
    "Policy",
    "GovernanceResult",
    "Decision",
    # Output guard
    "OutputGuard",
    "OutputGuardResult",
    "PHANTOM_ACTION_PATTERNS",
    # Posture
    "PostureEngine",
    "Posture",
    "PostureName",
    "CONSERVATIVE",
    "BALANCED",
    "AGGRESSIVE",
]
