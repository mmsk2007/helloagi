"""Governance surface — SRG and its peers.

Hello AGI's moat is governed autonomy. This package is the enforcement
surface: the deterministic, prompt-injection-immune Python layer that
every autonomous action flows through.

Public surface:

- :class:`SRGGovernor` — input-side gate: evaluates user text and
  individual tool-call intents before execution.
- :class:`OutputGuard` — output-side gate: scans tool outputs and agent
  text for secret leakage and phantom actions before emission.
- :class:`MemoryGuard` — write-side gate: sanitizes or denies content
  on its way into persistent memory; closes OWASP ASI06 (memory
  poisoning) by refusing to store raw poisoned input verbatim.
- :class:`PostureEngine` — derives a runtime :class:`Posture`
  (conservative / balanced / aggressive) per autonomous goal; posture
  scales thresholds, replan budget, and failure tolerance.

All four gates are pure Python and deterministic by design. The whole
point of the moat is that *no prompt can override Python*.
"""

from agi_runtime.governance.memory_guard import (
    MemoryDecision,
    MemoryGuard,
    MemoryGuardResult,
    MemoryKind,
)
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
    # Memory guard
    "MemoryGuard",
    "MemoryGuardResult",
    "MemoryDecision",
    "MemoryKind",
    # Posture
    "PostureEngine",
    "Posture",
    "PostureName",
    "CONSERVATIVE",
    "BALANCED",
    "AGGRESSIVE",
]
