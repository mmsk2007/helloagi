"""SRG Adapter — unified governance interface for new modules.

Instead of each new module (Skill Bank, Reliability Layer, Context Manager,
Browser Engine) independently importing SRGGovernor, OutputGuard, and
MemoryGuard, they call ``SRGAdapter.check_*()`` which dispatches to the
right gate and logs via GovernanceLogger.

This is a **facade**, not a replacement.  The underlying SRGGovernor,
OutputGuard, and MemoryGuard are untouched.  The adapter:
  1. Provides a single object to inject into new modules.
  2. Ensures every governance decision is logged.
  3. Adds convenience for new gate types (skill, browser, completion).

Usage::

    adapter = SRGAdapter(governor, output_guard, memory_guard, journal)

    # Check user input
    result = adapter.check_input("help me plan a launch", principal_id="u1")

    # Check tool call
    result = adapter.check_tool("bash_exec", {"command": "ls"}, "medium")

    # Check agent output
    result = adapter.check_output("I created the file", tool_calls_made=1)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from agi_runtime.governance.governance_logger import GovernanceLogger, GovernanceRecord
from agi_runtime.governance.srg import GovernanceResult, SRGGovernor
from agi_runtime.governance.output_guard import OutputGuard, OutputGuardResult
from agi_runtime.governance.memory_guard import MemoryGuard
from agi_runtime.observability.journal import Journal
from agi_runtime.skills.skill_schema import SkillContract


@dataclass
class AdapterResult:
    """Unified result from any governance check."""

    allowed: bool
    decision: str       # "allow", "deny", "escalate", "redact"
    risk: float
    reasons: List[str]
    record: Optional[GovernanceRecord] = None
    # For output checks: the redacted text if decision is "redact"
    redacted_text: Optional[str] = None

    @property
    def denied(self) -> bool:
        return self.decision == "deny"

    @property
    def escalated(self) -> bool:
        return self.decision == "escalate"


class SRGAdapter:
    """Unified governance facade for new HelloAGI modules.

    Composes SRGGovernor + OutputGuard + MemoryGuard + GovernanceLogger
    into a single interface.  Existing modules continue using the raw
    SRGGovernor directly — this adapter is for NEW code only.
    """

    def __init__(
        self,
        governor: Optional[SRGGovernor] = None,
        output_guard: Optional[OutputGuard] = None,
        memory_guard: Optional[MemoryGuard] = None,
        journal: Optional[Journal] = None,
    ):
        self.governor = governor or SRGGovernor()
        self.output_guard = output_guard or OutputGuard()
        self.memory_guard = memory_guard or MemoryGuard()
        self.logger = GovernanceLogger(journal)

    # ── Input Gate ───────────────────────────────────────────────

    def check_input(
        self,
        text: str,
        *,
        principal_id: str = "",
        posture: str = "",
    ) -> AdapterResult:
        """Evaluate user input through SRG and log the decision."""
        gov = self.governor.evaluate(text)
        record = self.logger.log_input_gate(
            decision=gov.decision,
            risk=gov.risk,
            reasons=list(gov.reasons),
            user_input=text,
            principal_id=principal_id,
            posture=posture,
        )
        return AdapterResult(
            allowed=gov.decision == "allow",
            decision=gov.decision,
            risk=gov.risk,
            reasons=list(gov.reasons),
            record=record,
        )

    # ── Tool Gate ────────────────────────────────────────────────

    def check_tool(
        self,
        tool_name: str,
        tool_input: dict | None = None,
        risk_level: str = "medium",
        *,
        principal_id: str = "",
        posture: str = "",
    ) -> AdapterResult:
        """Evaluate a tool call through SRG and log the decision."""
        gov = self.governor.evaluate_tool(
            tool_name, tool_input or {}, risk_level,
        )
        record = self.logger.log_tool_gate(
            decision=gov.decision,
            risk=gov.risk,
            reasons=list(gov.reasons),
            tool_name=tool_name,
            tool_input=tool_input,
            principal_id=principal_id,
            posture=posture,
        )
        return AdapterResult(
            allowed=gov.decision == "allow",
            decision=gov.decision,
            risk=gov.risk,
            reasons=list(gov.reasons),
            record=record,
        )

    # ── Output Gate ──────────────────────────────────────────────

    def check_output(
        self,
        text: str,
        *,
        tool_calls_made: Optional[int] = None,
        principal_id: str = "",
    ) -> AdapterResult:
        """Inspect agent output through OutputGuard and log the decision."""
        guard = self.output_guard.inspect(text, tool_calls_made=tool_calls_made)
        record = self.logger.log_output_gate(
            decision=guard.decision,
            reasons=list(guard.reasons),
            signal_count=guard.signal_count,
            text_preview=text[:200] if text else "",
            principal_id=principal_id,
        )
        return AdapterResult(
            allowed=guard.decision == "allow",
            decision=guard.decision,
            risk=0.0,
            reasons=list(guard.reasons),
            record=record,
            redacted_text=guard.redacted_text,
        )

    # ── Memory Gate ──────────────────────────────────────────────

    def check_memory(
        self,
        content: str,
        memory_type: str = "general",
        *,
        principal_id: str = "",
    ) -> AdapterResult:
        """Inspect a memory write through MemoryGuard and log the decision."""
        result = self.memory_guard.inspect(content, memory_type=memory_type)
        record = self.logger.log_memory_gate(
            decision=result.decision,
            reasons=list(result.reasons),
            memory_type=memory_type,
            content_preview=content[:150] if content else "",
            principal_id=principal_id,
        )
        return AdapterResult(
            allowed=result.decision in ("allow", "sanitize"),
            decision=result.decision,
            risk=0.0,
            reasons=list(result.reasons),
            record=record,
            redacted_text=result.sanitized if hasattr(result, "sanitized") else None,
        )

    def check_skill_promotion(
        self,
        contract: SkillContract,
        *,
        principal_id: str = "",
    ) -> AdapterResult:
        """Memory-gate a skill contract before persisting to the skill bank."""
        payload = contract.to_json()
        return self.check_memory(
            payload[:8000],
            memory_type="skill",
            principal_id=principal_id,
        )

    # ── Generic Gate (for new gate types) ────────────────────────

    def check_generic(
        self,
        gate: str,
        text: str,
        *,
        principal_id: str = "",
        posture: str = "",
    ) -> AdapterResult:
        """Run text through SRG evaluate() for a custom gate type and log."""
        gov = self.governor.evaluate(text)
        record = self.logger.log_generic(
            gate=gate,
            decision=gov.decision,
            risk=gov.risk,
            reasons=list(gov.reasons),
            action_summary=text[:200] if text else "",
            principal_id=principal_id,
        )
        return AdapterResult(
            allowed=gov.decision == "allow",
            decision=gov.decision,
            risk=gov.risk,
            reasons=list(gov.reasons),
            record=record,
        )

    # ── Accessors ────────────────────────────────────────────────

    def get_governance_summary(self) -> dict:
        """Get a summary of all governance decisions in this session."""
        return self.logger.get_summary()

    def get_records(self, **kwargs) -> list:
        """Query governance records (delegates to GovernanceLogger)."""
        return self.logger.get_records(**kwargs)


__all__ = ["SRGAdapter", "AdapterResult"]
