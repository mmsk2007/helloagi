"""Governance Logger — dedicated audit trail for all SRG governance decisions.

Every governance decision (input gate, tool gate, output gate, memory gate,
completion gate) is recorded as a first-class ``GovernanceRecord``.  Records
are written to the Journal under the ``governance.*`` kind namespace so
they can be filtered, replayed, and audited independently of general events.

This module is additive: it does NOT modify any existing SRG code.  It wraps
the existing SRGGovernor/OutputGuard/MemoryGuard and adds structured logging.

Design:
    - Pure dataclass records — serializable, testable, deterministic.
    - Writes to the shared Journal (no separate log file — keeps repo clean).
    - Filtering by gate type, decision, risk range, and principal.
    - Thread-safe (Journal is append-only JSONL).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import List, Literal, Optional

from agi_runtime.observability.journal import Journal


GateType = Literal[
    "input",        # SRGGovernor.evaluate() on user input
    "tool",         # SRGGovernor.evaluate_tool() on tool calls
    "output",       # OutputGuard.inspect() on agent responses
    "memory",       # MemoryGuard.inspect() on memory writes
    "completion",   # Completion verification (Milestone 3)
    "plan",         # SRG evaluation of serialized plans (TriLoop)
    "step",         # SRG evaluation of individual plan steps (TriLoop)
    "skill",        # SRG evaluation of skill creation/promotion
    "browser",      # Browser-specific governance (Milestone 5)
    "recovery",     # Recovery strategy switch governance (Milestone 3)
]

Decision = Literal["allow", "deny", "escalate", "redact", "require_more_evidence"]


@dataclass
class GovernanceRecord:
    """One governance decision — the atomic unit of the audit trail."""

    timestamp: float
    gate: GateType
    decision: Decision
    risk: float
    reasons: List[str] = field(default_factory=list)
    action_summary: str = ""
    principal_id: str = ""
    tool_name: str = ""
    outcome: str = ""           # "proceeded", "blocked", "user_approved", "user_denied"
    signal_count: int = 0       # For output guard — how many patterns fired
    posture: str = ""           # The active posture when the decision was made
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize for Journal storage."""
        d = asdict(self)
        # Drop empty fields to keep records compact
        return {k: v for k, v in d.items() if v or v == 0}


class GovernanceLogger:
    """Records governance decisions to the Journal.

    Usage::

        logger = GovernanceLogger(journal)
        logger.log_input_gate(gov_result, user_input, principal_id="user-123")
        logger.log_tool_gate(gov_result, tool_name="bash_exec", tool_input={...})
        logger.log_output_gate(guard_result, text_preview="I created the file...")

    All methods are fire-and-forget: logging failures never crash the caller.
    """

    def __init__(self, journal: Optional[Journal] = None):
        self._journal = journal
        self._records: List[GovernanceRecord] = []
        self._max_in_memory = 1000  # Rolling window for filtering

    @property
    def journal(self) -> Optional[Journal]:
        return self._journal

    @journal.setter
    def journal(self, j: Optional[Journal]) -> None:
        self._journal = j

    # ── Gate-specific convenience methods ────────────────────────

    def log_input_gate(
        self,
        decision: str,
        risk: float,
        reasons: List[str],
        user_input: str = "",
        principal_id: str = "",
        posture: str = "",
    ) -> GovernanceRecord:
        """Record an input-side SRG evaluation."""
        return self._record(
            gate="input",
            decision=_norm_decision(decision),
            risk=risk,
            reasons=list(reasons),
            action_summary=_clip(user_input, 200),
            principal_id=principal_id,
            posture=posture,
        )

    def log_tool_gate(
        self,
        decision: str,
        risk: float,
        reasons: List[str],
        tool_name: str = "",
        tool_input: dict | None = None,
        principal_id: str = "",
        posture: str = "",
    ) -> GovernanceRecord:
        """Record a tool-call SRG evaluation."""
        summary = f"{tool_name}({_clip(str(tool_input or {}), 150)})"
        return self._record(
            gate="tool",
            decision=_norm_decision(decision),
            risk=risk,
            reasons=list(reasons),
            action_summary=summary,
            tool_name=tool_name,
            principal_id=principal_id,
            posture=posture,
        )

    def log_output_gate(
        self,
        decision: str,
        reasons: List[str],
        signal_count: int = 0,
        text_preview: str = "",
        principal_id: str = "",
    ) -> GovernanceRecord:
        """Record an OutputGuard inspection."""
        return self._record(
            gate="output",
            decision=_norm_decision(decision),
            risk=0.0,  # OutputGuard doesn't compute risk scores
            reasons=list(reasons),
            action_summary=_clip(text_preview, 200),
            signal_count=signal_count,
            principal_id=principal_id,
        )

    def log_memory_gate(
        self,
        decision: str,
        reasons: List[str],
        memory_type: str = "",
        content_preview: str = "",
        principal_id: str = "",
    ) -> GovernanceRecord:
        """Record a MemoryGuard inspection."""
        return self._record(
            gate="memory",
            decision=_norm_decision(decision),
            risk=0.0,
            reasons=list(reasons),
            action_summary=f"[{memory_type}] {_clip(content_preview, 150)}",
            principal_id=principal_id,
        )

    def log_generic(
        self,
        gate: str,
        decision: str,
        risk: float = 0.0,
        reasons: List[str] | None = None,
        action_summary: str = "",
        principal_id: str = "",
        **extra: object,
    ) -> GovernanceRecord:
        """Record a governance decision for any gate type."""
        return self._record(
            gate=gate,
            decision=_norm_decision(decision),
            risk=risk,
            reasons=list(reasons or []),
            action_summary=_clip(action_summary, 200),
            principal_id=principal_id,
            extra={k: str(v) for k, v in extra.items()},
        )

    # ── Query / filtering ────────────────────────────────────────

    def get_records(
        self,
        *,
        gate: str | None = None,
        decision: str | None = None,
        principal_id: str | None = None,
        min_risk: float | None = None,
        last_n: int | None = None,
    ) -> List[GovernanceRecord]:
        """Filter in-memory records. Useful for diagnostics and testing."""
        out = list(self._records)
        if gate:
            out = [r for r in out if r.gate == gate]
        if decision:
            out = [r for r in out if r.decision == decision]
        if principal_id:
            out = [r for r in out if r.principal_id == principal_id]
        if min_risk is not None:
            out = [r for r in out if r.risk >= min_risk]
        if last_n is not None:
            out = out[-last_n:]
        return out

    def get_summary(self) -> dict:
        """Quick summary of governance activity."""
        total = len(self._records)
        by_decision: dict[str, int] = {}
        by_gate: dict[str, int] = {}
        for r in self._records:
            by_decision[r.decision] = by_decision.get(r.decision, 0) + 1
            by_gate[r.gate] = by_gate.get(r.gate, 0) + 1
        return {
            "total_records": total,
            "by_decision": by_decision,
            "by_gate": by_gate,
        }

    def clear(self) -> None:
        """Clear in-memory records (does not affect Journal)."""
        self._records.clear()

    # ── Internal ─────────────────────────────────────────────────

    def _record(self, **kwargs: object) -> GovernanceRecord:
        """Create, store, and journal a governance record."""
        rec = GovernanceRecord(timestamp=time.time(), **kwargs)  # type: ignore[arg-type]
        self._records.append(rec)
        # Trim rolling window
        if len(self._records) > self._max_in_memory:
            self._records = self._records[-self._max_in_memory:]
        # Write to Journal (fire-and-forget)
        self._write_journal(rec)
        return rec

    def _write_journal(self, rec: GovernanceRecord) -> None:
        if self._journal is None:
            return
        try:
            kind = f"governance.{rec.gate}.{rec.decision}"
            self._journal.write(kind, rec.to_dict())
        except Exception:
            pass  # Logging must never crash the runtime


# ── Helpers ──────────────────────────────────────────────────────

def _clip(s: str, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[:n - 3] + "..."


def _norm_decision(d: str) -> str:
    """Normalize decision strings from various sources."""
    d = d.lower().strip()
    if d in ("allow", "deny", "escalate", "redact", "require_more_evidence"):
        return d
    if d == "sanitize":
        return "redact"
    if d == "block":
        return "deny"
    return d


__all__ = ["GovernanceLogger", "GovernanceRecord", "GateType", "Decision"]
