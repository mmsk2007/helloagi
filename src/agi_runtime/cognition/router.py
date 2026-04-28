"""CognitiveRouter — chooses System 1 (Expert) or System 2 (Thinking) per task.

The router is the front door of the cognitive runtime. Given a user input and
its SRG governance result, it decides whether the existing fast path is good
enough or whether the task needs deeper deliberation.

Three operating modes (config-gated, reversible at any time):

  - "observe"      Phase 1 — compute a decision, log it, change nothing.
  - "system1_only" Phase 2 — route familiar+safe tasks to Expert Mode; everything
                   else falls through to today's default loop.
  - "dual"         Phase 3 — route to Expert or Council based on familiarity
                   and risk. Council = full System 2.

The decision itself is deterministic for a given (input, skill_state, posture,
breaker_state) — replays are sound. SRG can veto System 1 by returning
"escalate" or "deny" upstream; this router does not override SRG.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from agi_runtime.cognition.fingerprint import task_fingerprint
from agi_runtime.cognition.risk import RiskScorer, RiskSignals
from agi_runtime.governance.srg import GovernanceResult


RouterMode = Literal["observe", "system1_only", "dual"]
SystemChoice = Literal["system1", "system2"]


@dataclass
class RoutingDecision:
    """The router's verdict for one task. Logged verbatim to the journal."""

    system: SystemChoice
    reason: str
    fingerprint: str
    posture: str
    risk: float
    risk_signals: RiskSignals = field(default_factory=RiskSignals)
    skill_match_name: Optional[str] = None
    skill_match_relevance: Optional[float] = None
    skill_match_confidence: Optional[float] = None
    srg_decision: str = "allow"
    mode: RouterMode = "observe"
    # Whether the decision actually changed execution flow. In "observe" mode
    # this is always False — useful when grepping the journal for "did the
    # router *do* anything yet?".
    enforced: bool = False
    ts: float = field(default_factory=time.time)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "system": self.system,
            "reason": self.reason,
            "fingerprint": self.fingerprint,
            "posture": self.posture,
            "risk": self.risk,
            "risk_signals": {
                "srg": self.risk_signals.srg_risk,
                "posture_floor": self.risk_signals.posture_floor,
                "tool_health": self.risk_signals.tool_health_risk,
                "novelty": self.risk_signals.novelty_risk,
                "contributing": list(self.risk_signals.contributing),
            },
            "skill": (
                {
                    "name": self.skill_match_name,
                    "relevance": self.skill_match_relevance,
                    "confidence": self.skill_match_confidence,
                }
                if self.skill_match_name
                else None
            ),
            "srg_decision": self.srg_decision,
            "mode": self.mode,
            "enforced": self.enforced,
            "ts": self.ts,
        }


_DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "mode": "observe",
    "system1_relevance_threshold": 0.75,
    "system1_confidence_threshold": 0.70,
    "risk_escalation_threshold": 0.50,
    "novelty_lookback_events": 200,
}


class CognitiveRouter:
    """Decides System 1 vs System 2 for each task.

    The router is *advisory* in observe mode: it never raises, never blocks,
    and never alters output. Callers that need enforcement query
    ``decision.enforced`` and branch accordingly.
    """

    def __init__(
        self,
        *,
        skills: Any = None,           # SkillManager (duck-typed for testability)
        journal: Any = None,          # Journal (duck-typed)
        event_bus: Any = None,        # EventBus (optional)
        risk_scorer: Optional[RiskScorer] = None,
        config: Optional[Dict[str, Any]] = None,
        recent_fingerprints: Optional[List[str]] = None,
    ):
        self.skills = skills
        self.journal = journal
        self.event_bus = event_bus
        self.risk_scorer = risk_scorer or RiskScorer()
        self._config: Dict[str, Any] = {**_DEFAULT_CONFIG, **(config or {})}
        # In-memory novelty cache. Populated lazily by ``observe_outcome`` or
        # seeded from the journal at boot. Bounded by lookback window.
        self._seen_fingerprints: Dict[str, float] = {}
        if recent_fingerprints:
            now = time.time()
            for fp in recent_fingerprints[-self.lookback_window :]:
                self._seen_fingerprints[fp] = now

    # ── Configuration ─────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("enabled", False))

    @property
    def mode(self) -> RouterMode:
        m = self._config.get("mode", "observe")
        return m if m in ("observe", "system1_only", "dual") else "observe"

    @property
    def lookback_window(self) -> int:
        return int(self._config.get("novelty_lookback_events", 200) or 200)

    def update_config(self, config: Dict[str, Any]) -> None:
        self._config.update(config or {})

    # ── Decision API ──────────────────────────────────────────────

    def decide(
        self,
        user_input: str,
        gov: GovernanceResult,
        *,
        posture_name: str = "balanced",
        task_type: str = "",
    ) -> RoutingDecision:
        """Compute the routing decision and emit a journal/event entry.

        The decision is always returned. Whether it is *enforced* depends on
        the active mode:

          - observe        → never enforced (logged, ignored)
          - system1_only   → enforced only when the verdict is system1
          - dual           → always enforced
        """

        fingerprint = task_fingerprint(user_input, task_type=task_type)
        is_novel = fingerprint not in self._seen_fingerprints

        # Skill match — best candidate from the bank for this query.
        match_name = None
        match_relevance = None
        match_confidence = None
        suggested_tools: List[str] = []
        if self.skills is not None and hasattr(self.skills, "find_matching_skill_semantic"):
            try:
                matches = self.skills.find_matching_skill_semantic(user_input, top_k=1)
            except Exception:
                matches = []
            if matches:
                top = matches[0]
                match_name = getattr(top.skill, "name", None)
                match_relevance = float(getattr(top, "relevance", 0.0) or 0.0)
                match_confidence = float(
                    getattr(top.skill, "confidence_score", 0.0) or 0.0
                )
                suggested_tools = list(
                    getattr(top.skill, "tools_required", []) or []
                )

        risk, signals = self.risk_scorer.score(
            gov,
            posture_name=posture_name,
            suggested_tools=suggested_tools,
            is_novel=is_novel,
        )

        srg_decision = getattr(gov, "decision", "allow") or "allow"

        system, reason = self._verdict(
            srg_decision=srg_decision,
            risk=risk,
            relevance=match_relevance,
            confidence=match_confidence,
        )

        enforced = self.enabled and self._is_enforced(system)

        decision = RoutingDecision(
            system=system,
            reason=reason,
            fingerprint=fingerprint,
            posture=posture_name,
            risk=risk,
            risk_signals=signals,
            skill_match_name=match_name,
            skill_match_relevance=match_relevance,
            skill_match_confidence=match_confidence,
            srg_decision=srg_decision,
            mode=self.mode,
            enforced=enforced,
        )

        self._log(decision)
        self._record_seen(fingerprint)
        return decision

    def observe_outcome(self, fingerprint: str) -> None:
        """Record that we've now executed something with this fingerprint.

        Phase 1+ uses this to drive the novelty signal. Phases 2/3 will also
        feed it into the feedback loop (``cognition.feedback``).
        """
        if fingerprint:
            self._record_seen(fingerprint)

    # ── Internals ─────────────────────────────────────────────────

    def _verdict(
        self,
        *,
        srg_decision: str,
        risk: float,
        relevance: Optional[float],
        confidence: Optional[float],
    ) -> tuple[SystemChoice, str]:
        # SRG escalate already implies "needs more deliberation".
        if srg_decision == "escalate":
            return "system2", "srg-escalate"

        if risk >= float(self._config["risk_escalation_threshold"]):
            return "system2", f"risk>={self._config['risk_escalation_threshold']}"

        rel_th = float(self._config["system1_relevance_threshold"])
        conf_th = float(self._config["system1_confidence_threshold"])
        if relevance is None or confidence is None:
            return "system2", "no-skill-match"
        if relevance >= rel_th and confidence >= conf_th:
            return (
                "system1",
                f"familiar (rel={relevance:.2f}>={rel_th:.2f}, conf={confidence:.2f}>={conf_th:.2f})",
            )
        return (
            "system2",
            f"unfamiliar (rel={relevance:.2f}<{rel_th:.2f} or conf={confidence:.2f}<{conf_th:.2f})",
        )

    def _is_enforced(self, system: SystemChoice) -> bool:
        m = self.mode
        if m == "observe":
            return False
        if m == "system1_only":
            return system == "system1"
        # dual
        return True

    def _record_seen(self, fingerprint: str) -> None:
        self._seen_fingerprints[fingerprint] = time.time()
        # Bound memory: drop oldest beyond the lookback window.
        if len(self._seen_fingerprints) > self.lookback_window:
            ordered = sorted(self._seen_fingerprints.items(), key=lambda kv: kv[1])
            for fp, _ in ordered[: len(ordered) - self.lookback_window]:
                self._seen_fingerprints.pop(fp, None)

    def _log(self, decision: RoutingDecision) -> None:
        payload = decision.to_payload()
        if self.journal is not None and hasattr(self.journal, "write"):
            try:
                self.journal.write("routing.decided", payload)
            except Exception:
                pass
        if self.event_bus is not None and hasattr(self.event_bus, "emit"):
            try:
                self.event_bus.emit("routing.decided", payload)
            except Exception:
                pass


__all__ = ["CognitiveRouter", "RoutingDecision", "RouterMode"]
