"""OutcomeRecorder — feeds System 1 (and later, System 2) results back into the
skill bank and the journal.

The router only learns when callers tell it what happened. ``record_system1``
is the System 1 half of that loop:

  - Increments per-skill ``system1_success_count`` / ``system1_failure_count``.
  - Calls the skill's existing ``record_success`` / ``record_failure`` so the
    overall ``confidence_score`` updates with the same recency math the rest
    of the lifecycle uses.
  - Persists the skill via ``SkillBank.persist`` if a bank is wired in.
  - Logs ``system1.outcome`` to the journal for replay/audit.

Phase 4 will add ``record_system2`` (council outcomes + per-agent vote weights);
the shape mirrors this.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from agi_runtime.cognition.system1 import ExpertOverrides
from agi_runtime.cognition.trace import CouncilTrace, ThinkingTraceStore


@dataclass
class OutcomeReport:
    """Compact record of one System-1 attempt — what we logged, what changed."""

    system: str = "system1"
    fingerprint: str = ""
    skill_name: str = ""
    success: bool = False
    new_confidence: Optional[float] = None
    new_status: Optional[str] = None
    failure_reason: str = ""
    ts: float = field(default_factory=time.time)

    def to_payload(self) -> dict:
        return {
            "system": self.system,
            "fingerprint": self.fingerprint,
            "skill": self.skill_name,
            "success": self.success,
            "new_confidence": self.new_confidence,
            "new_status": self.new_status,
            "failure_reason": self.failure_reason,
            "ts": self.ts,
        }


# Below this success rate (with enough samples) the skill auto-demotes from
# "active" to "candidate", blocking future System 1 firings until the council
# reproves it. We use success_rate, not confidence_score, on purpose:
# confidence_score includes a recency bonus that floors around 0.30 for any
# actively-used skill, which would mask a streak of failures. success_rate is
# recency-free — one bad day still won't demote, but a streak with enough
# samples will.
_RETIRE_SUCCESS_RATE_FLOOR = 0.25
_RETIRE_MIN_USES = 5


class OutcomeRecorder:
    """Logs System-1 outcomes and updates the underlying SkillContract.

    All inputs are duck-typed for testability. Pass real ``SkillManager`` /
    ``Journal`` / ``EventBus`` instances in production; pass fakes in tests.
    """

    def __init__(
        self,
        *,
        skills: Any = None,        # SkillManager
        journal: Any = None,
        event_bus: Any = None,
        trace_store: Optional[ThinkingTraceStore] = None,
        vote_weights: Any = None,  # VoteWeights — Phase 4 will mutate
        crystallizer: Any = None,  # SkillCrystallizer — System 2 successes train System 1
    ):
        self.skills = skills
        self.journal = journal
        self.event_bus = event_bus
        self.trace_store = trace_store
        self.vote_weights = vote_weights
        self.crystallizer = crystallizer

    def record_system1(
        self,
        overrides: ExpertOverrides,
        *,
        success: bool,
        failure_reason: str = "",
    ) -> OutcomeReport:
        report = OutcomeReport(
            system="system1",
            fingerprint=overrides.fingerprint,
            skill_name=overrides.skill_name,
            success=success,
            failure_reason=failure_reason if not success else "",
        )

        contract = self._lookup_contract(overrides.skill_name)
        if contract is not None:
            if success:
                contract.system1_success_count = (
                    int(getattr(contract, "system1_success_count", 0) or 0) + 1
                )
                contract.record_success()
            else:
                contract.system1_failure_count = (
                    int(getattr(contract, "system1_failure_count", 0) or 0) + 1
                )
                # Tag the failure mode so it shows up in the contract's audit.
                tag = f"system1:{failure_reason or 'unknown'}"
                contract.record_failure(tag)
                if (
                    contract.success_rate < _RETIRE_SUCCESS_RATE_FLOOR
                    and contract.usage_count >= _RETIRE_MIN_USES
                    and contract.status == "active"
                ):
                    contract.status = "candidate"
                    report.new_status = "candidate"
            report.new_confidence = contract.confidence_score
            self._persist_contract(contract)
            if report.new_status is None:
                report.new_status = contract.status

        self._log(report)
        return report

    def record_system2(
        self,
        trace: CouncilTrace,
        *,
        success: bool,
        failure_reason: str = "",
    ) -> OutcomeReport:
        """Persist a System 2 outcome and run the self-improvement nudges.

        Three things happen here, in order:
          1. The trace's ``outcome`` is patched in the trace store.
          2. Per-agent vote weights are nudged: an agent whose vote matched
             the verified outcome gets boosted; one that didn't gets
             trimmed. Clamped via ``VoteWeights`` so a single bad run
             can't wreck calibration.
          3. ``system2.outcome`` is journaled (and emitted to the bus) for
             downstream subscribers like the SkillCrystallizer.

        Crystallization itself runs from ``maybe_crystallize`` further down
        — keeping it here would couple feedback to skill creation, and the
        crystallizer needs to be opt-in.
        """
        outcome_label = "pass" if success else ("fail" if failure_reason else "partial")
        report = OutcomeReport(
            system="system2",
            fingerprint=trace.fingerprint,
            skill_name="",
            success=success,
            failure_reason=failure_reason if not success else "",
        )
        if self.trace_store is not None:
            try:
                self.trace_store.update_outcome(trace.trace_id, outcome_label)
            except Exception:
                pass
        self._nudge_agent_weights(trace, success=success)
        self._log_system2(trace, report, outcome_label)
        if success:
            self._maybe_crystallize(trace)
        return report

    def _maybe_crystallize(self, trace: CouncilTrace) -> None:
        """After a verified pass, ask the crystallizer whether this
        fingerprint has earned a System 1 skill.  Best-effort — never
        let crystallization fail block the user-facing outcome path.
        """
        if self.crystallizer is None or not getattr(trace, "fingerprint", ""):
            return
        try:
            self.crystallizer.maybe_crystallize(trace.fingerprint)
        except Exception:
            pass

    def _nudge_agent_weights(self, trace: CouncilTrace, *, success: bool) -> None:
        """Apply outcome-driven weight nudges to the council's last-round
        voters. No-op if no VoteWeights store is wired in.
        """
        if self.vote_weights is None or not trace.rounds:
            return
        last_votes = trace.rounds[-1].votes or {}
        try:
            from agi_runtime.cognition.system2.voting import nudge_weights_from_outcome
            nudge_weights_from_outcome(
                weights=self.vote_weights,
                last_round_votes=last_votes,
                success=success,
            )
        except Exception:
            # Weight calibration is best-effort. A failure here must not
            # poison the outcome write or the journal entry.
            pass

    def _log_system2(
        self, trace: CouncilTrace, report: OutcomeReport, outcome_label: str
    ) -> None:
        payload = {
            "system": "system2",
            "trace_id": trace.trace_id,
            "fingerprint": trace.fingerprint,
            "outcome": outcome_label,
            "success": report.success,
            "failure_reason": report.failure_reason,
            "ts": report.ts,
        }
        if self.journal is not None and hasattr(self.journal, "write"):
            try:
                self.journal.write("system2.outcome", payload)
            except Exception:
                pass
        if self.event_bus is not None and hasattr(self.event_bus, "emit"):
            try:
                self.event_bus.emit("system2.outcome", payload)
            except Exception:
                pass

    # ── Internals ─────────────────────────────────────────────────

    def _lookup_contract(self, name: str):
        if not name or self.skills is None:
            return None
        bank = getattr(self.skills, "skill_bank", None) or getattr(
            self.skills, "bank", None
        )
        if bank is None or not hasattr(bank, "get_by_name"):
            return None
        try:
            return bank.get_by_name(name)
        except Exception:
            return None

    def _persist_contract(self, contract) -> None:
        bank = getattr(self.skills, "skill_bank", None) or getattr(
            self.skills, "bank", None
        )
        if bank is None or not hasattr(bank, "persist"):
            return
        try:
            bank.persist(contract)
        except Exception:
            # Persistence failure is logged at the bank layer; keep going.
            pass

    def _log(self, report: OutcomeReport) -> None:
        payload = report.to_payload()
        if self.journal is not None and hasattr(self.journal, "write"):
            try:
                self.journal.write("system1.outcome", payload)
            except Exception:
                pass
        if self.event_bus is not None and hasattr(self.event_bus, "emit"):
            try:
                self.event_bus.emit("system1.outcome", payload)
            except Exception:
                pass


__all__ = ["OutcomeRecorder", "OutcomeReport"]
