"""Cognitive runtime — dual-system (System 1 / System 2) routing.

Mirrors fast/slow human cognition:
- System 1 (Expert Mode): fast, cheap path for familiar tasks, backed by Skills.
- System 2 (Thinking Mode): deeper reasoning for novel/risky tasks, executed by an
  Agent Council that debates and records a queryable trace.

This package is the core runtime component that wraps the existing agent loop.
With cognitive_runtime.enabled=False (default), behavior is identical to today.
"""

from agi_runtime.cognition.fingerprint import task_fingerprint, normalize_task_text
from agi_runtime.cognition.risk import RiskScorer, RiskSignals
from agi_runtime.cognition.router import (
    CognitiveRouter,
    RoutingDecision,
    RouterMode,
)
from agi_runtime.cognition.system1 import (
    ExpertOverrides,
    prepare_expert_overrides,
    EXPERT_MODEL_ID,
)
from agi_runtime.cognition.feedback import OutcomeRecorder, OutcomeReport

__all__ = [
    "task_fingerprint",
    "normalize_task_text",
    "RiskScorer",
    "RiskSignals",
    "CognitiveRouter",
    "RoutingDecision",
    "RouterMode",
    "ExpertOverrides",
    "prepare_expert_overrides",
    "EXPERT_MODEL_ID",
    "OutcomeRecorder",
    "OutcomeReport",
]
