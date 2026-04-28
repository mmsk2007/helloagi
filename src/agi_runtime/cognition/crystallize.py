"""SkillCrystallizer — turns repeated System 2 wins into a System 1 skill.

Phase 4c. The contract:

  - Subscribed (via ``OutcomeRecorder``) to every System 2 pass.
  - On each pass, ``maybe_crystallize(fingerprint)`` walks the trace
    store for that fingerprint, counts how many traces have
    ``outcome == "pass"``, and computes the average inter-agent
    agreement of those passing rounds.
  - If both gates clear (``min_council_successes`` and
    ``min_agent_agreement``), the most recent passing trace is fed to
    ``SkillExtractor.extract_from_council_trace`` and the resulting
    candidate is persisted in the SkillBank. The router will pick it
    up on the next matching fingerprint and route to System 1.
  - Idempotent: if a skill already exists for this fingerprint we
    refresh its provenance and confidence, but never duplicate.

We keep this off the hot path. The OutcomeRecorder calls this *after*
the user-facing turn returns, so a slow filesystem write or a failing
extraction never delays a response.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, List, Optional

from agi_runtime.cognition.trace import CouncilTrace, ThinkingTraceStore
from agi_runtime.skills.skill_extractor import SkillExtractor
from agi_runtime.skills.skill_schema import SkillContract


_DEFAULT_MIN_SUCCESSES = 3
_DEFAULT_MIN_AGREEMENT = 0.66


@dataclass
class CrystallizationReport:
    """What the crystallizer just did, surfaced for journaling/tests."""

    crystallized: bool
    fingerprint: str
    successes: int
    agreement: float
    skill_id: str = ""
    skill_name: str = ""
    reason: str = ""

    def to_payload(self) -> dict:
        return {
            "crystallized": self.crystallized,
            "fingerprint": self.fingerprint,
            "successes": self.successes,
            "agreement": round(self.agreement, 3),
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "reason": self.reason,
            "ts": time.time(),
        }


class SkillCrystallizer:
    """Promote a fingerprint's recurring council wins into a SkillContract."""

    def __init__(
        self,
        *,
        trace_store: Optional[ThinkingTraceStore] = None,
        skill_bank: Any = None,
        extractor: Optional[SkillExtractor] = None,
        journal: Any = None,
        event_bus: Any = None,
        min_council_successes: int = _DEFAULT_MIN_SUCCESSES,
        min_agent_agreement: float = _DEFAULT_MIN_AGREEMENT,
    ):
        self.trace_store = trace_store
        self.skill_bank = skill_bank
        self.extractor = extractor or SkillExtractor()
        self.journal = journal
        self.event_bus = event_bus
        self.min_successes = max(1, int(min_council_successes))
        self.min_agreement = float(min_agent_agreement)

    def maybe_crystallize(self, fingerprint: str) -> CrystallizationReport:
        """Inspect recent traces for ``fingerprint``; mint a Skill if the
        gates pass.  Always returns a report — callers use the
        ``crystallized`` flag rather than truthiness."""
        report = CrystallizationReport(
            crystallized=False, fingerprint=fingerprint, successes=0, agreement=0.0,
        )
        if not fingerprint or self.trace_store is None or self.skill_bank is None:
            report.reason = "missing_deps"
            return report

        traces = self.trace_store.find_by_fingerprint(fingerprint) or []
        passes = [t for t in traces if (t.outcome or "").lower() == "pass"]
        report.successes = len(passes)
        if len(passes) < self.min_successes:
            report.reason = "insufficient_successes"
            self._log(report)
            return report

        agreement = self._average_agreement(passes)
        report.agreement = agreement
        if agreement < self.min_agreement:
            report.reason = "low_agreement"
            self._log(report)
            return report

        # Newest pass wins as the canonical recipe — most recently
        # validated reasoning is the safest seed.
        seed = passes[0]
        skill = self.extractor.extract_from_council_trace(seed, agreement=agreement)
        if skill is None:
            report.reason = "extraction_failed"
            self._log(report)
            return report

        existing = self._existing_skill_for(fingerprint, skill.name)
        if existing is not None:
            self._refresh_existing(existing, skill, agreement, len(passes))
            report.crystallized = True
            report.skill_id = existing.skill_id
            report.skill_name = existing.name
            report.reason = "refreshed"
        else:
            saved = self.skill_bank.add(skill)
            report.crystallized = True
            report.skill_id = saved.skill_id if saved else skill.skill_id
            report.skill_name = skill.name
            report.reason = "created"

        self._log(report)
        return report

    # ── Internals ─────────────────────────────────────────────────

    def _average_agreement(self, traces: List[CouncilTrace]) -> float:
        """Mean fraction of non-abstain voters who landed on the winning
        side, taken over each trace's last round.

        Why last round only: the council can shift across rounds; the
        round that actually carried the decision is the one that
        matters for "did they really agree?".
        """
        if not traces:
            return 0.0
        scores: List[float] = []
        for t in traces:
            rounds = t.rounds or []
            if not rounds:
                continue
            last = rounds[-1]
            votes = getattr(last, "votes", {}) or {}
            yes = sum(1 for v in votes.values() if v == "yes")
            no = sum(1 for v in votes.values() if v == "no")
            non_abstain = yes + no
            if non_abstain == 0:
                continue
            scores.append(max(yes, no) / non_abstain)
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    def _existing_skill_for(
        self, fingerprint: str, name: str
    ) -> Optional[SkillContract]:
        if self.skill_bank is None:
            return None
        # Prefer a fingerprint match — names can collide between unrelated
        # tasks if the goal text is generic.
        if hasattr(self.skill_bank, "list_skills"):
            try:
                for s in self.skill_bank.list_skills():
                    if s.task_fingerprint and s.task_fingerprint == fingerprint:
                        return s
            except Exception:
                pass
        if hasattr(self.skill_bank, "get_by_name"):
            try:
                return self.skill_bank.get_by_name(name)
            except Exception:
                return None
        return None

    def _refresh_existing(
        self,
        existing: SkillContract,
        candidate: SkillContract,
        agreement: float,
        success_count: int,
    ) -> None:
        """Idempotent path. Don't blow away usage counters; do bump the
        confidence floor if more evidence accumulated."""
        if not existing.task_fingerprint:
            existing.task_fingerprint = candidate.task_fingerprint
        if candidate.council_origin_trace_id:
            existing.council_origin_trace_id = candidate.council_origin_trace_id
        # Confidence floor scales with how many corroborating successes
        # we now have, capped so manual edits aren't overridden.
        floor = min(0.85, candidate.confidence_score + 0.02 * max(0, success_count - 3))
        if existing.confidence_score < floor:
            existing.confidence_score = round(floor, 3)
        if not existing.execution_steps and candidate.execution_steps:
            existing.execution_steps = list(candidate.execution_steps)
        for tool in candidate.tools_required:
            if tool not in existing.tools_required:
                existing.tools_required.append(tool)
        try:
            self.skill_bank.persist(existing)
        except Exception:
            pass

    def _log(self, report: CrystallizationReport) -> None:
        payload = report.to_payload()
        if self.journal is not None and hasattr(self.journal, "write"):
            try:
                self.journal.write("skill.crystallized", payload)
            except Exception:
                pass
        if self.event_bus is not None and hasattr(self.event_bus, "emit"):
            try:
                self.event_bus.emit("skill.crystallized", payload)
            except Exception:
                pass


__all__ = ["SkillCrystallizer", "CrystallizationReport"]
