"""TriLoop — SRG-governed Plan → Execute → Verify → Replan.

This is the architectural backbone the docs promise but the code has been
missing. Before this module, Hello AGI's "autonomous loop" was a 17-line
statement repeater in ``autonomy/loop.py`` — it could not plan, could not
verify, and could not recover from failure. The planner and verifier existed
as standalone classes but nothing composed them.

The TriLoop composes them, and gates each phase with SRG:

    1. Pre-flight      — SRGGovernor.evaluate(goal) picks a posture.
    2. Plan            — Planner.make_plan(goal).
    3. Plan review     — SRG re-evaluates the serialized plan text
                         (posture.require_plan_review).
    4. Execute         — For each step (in dependency order):
                           - SRG evaluates the step's action text.
                           - Agent executes via .think(prompt).
                           - OutputGuard scans the response.
                           - Phantom-action detection via
                             AgentResponse.tool_calls_made.
    5. Verify          — Verifier.check(outputs, goal).
    6. Replan          — On PARTIAL/FAIL, Planner.replan(prev_plan,
                         failure_context) and loop back to (3). Bounded by
                         posture.max_replan_budget.

Every transition is journaled. Journals are the audit trail — replay tooling
can reconstruct the entire decision sequence.

The loop is agnostic to the concrete agent: it only requires a duck-typed
object with a ``.think(prompt) -> AgentResponse``-like method. That's what
makes it testable without an LLM.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Protocol

from agi_runtime.skills.skill_extractor import SkillExtractor

from agi_runtime.governance.output_guard import OutputGuard, OutputGuardResult
from agi_runtime.governance.posture import (
    BALANCED,
    Posture,
    PostureEngine,
    PostureName,
)
from agi_runtime.governance.srg import GovernanceResult, SRGGovernor
from agi_runtime.observability.journal import Journal
from agi_runtime.planner.planner import Plan, PlanStep, Planner
from agi_runtime.verifier.verifier import VerifyResult, Verifier


class _AgentLike(Protocol):
    """Minimal interface the TriLoop needs from an agent."""

    def think(self, user_input: str) -> Any:  # returns something with .text, .tool_calls_made
        ...


@dataclass
class StepTrace:
    """One row in the tri-loop's audit trail."""

    step_id: int
    action: str
    decision: str  # "allow" | "escalate" | "deny" | "executed" | "output-denied" | "output-redacted"
    srg_risk: float
    reasons: List[str] = field(default_factory=list)
    output: str = ""
    output_decision: str = "n/a"  # "allow" | "redact" | "deny" | "n/a"
    output_signals: int = 0
    tool_calls_made: int = 0
    duration_sec: float = 0.0
    error: Optional[str] = None


@dataclass
class IterationTrace:
    """One plan / execute / verify iteration of the loop."""

    iteration: int
    plan_reasoning: str
    steps: List[StepTrace] = field(default_factory=list)
    verify: Optional[VerifyResult] = None
    halted_reason: Optional[str] = None  # None if not halted early


TriLoopStatus = str  # "passed" | "exhausted" | "denied" | "plan_denied" | "replan_budget_exhausted"


@dataclass
class TriLoopResult:
    """Final result of a tri-loop run."""

    status: TriLoopStatus
    goal: str
    posture: Posture
    pre_flight: GovernanceResult
    iterations: List[IterationTrace] = field(default_factory=list)
    final_outputs: List[str] = field(default_factory=list)
    final_verdict: Optional[VerifyResult] = None
    total_duration_sec: float = 0.0
    # Set when status is "passed"; the successful plan, for learning.
    successful_plan: Optional[Plan] = None
    # Cognitive router decision recorded at start (observation-only in
    # autonomous mode for now — Phase 6 may use it to gate plan review).
    routing_decision: Optional[Any] = None

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def short_summary(self) -> str:
        v = self.final_verdict
        vstr = f"{v.status} (conf {v.confidence:.2f})" if v else "no-verdict"
        return (
            f"TriLoop[{self.status}] posture={self.posture.name} "
            f"iterations={len(self.iterations)} verdict={vstr} "
            f"duration={self.total_duration_sec:.2f}s"
        )


class TriLoop:
    """Plan → Execute → Verify → Replan, governed end-to-end by SRG.

    Usage::

        agent = HelloAGIAgent()
        loop = TriLoop(agent)
        result = loop.run("Draft a 3-step onboarding email series")
        if result.passed:
            return result.final_outputs
        else:
            handle_failure(result)
    """

    def __init__(
        self,
        agent: _AgentLike,
        *,
        governor: Optional[SRGGovernor] = None,
        planner: Optional[Planner] = None,
        verifier: Optional[Verifier] = None,
        output_guard: Optional[OutputGuard] = None,
        posture_engine: Optional[PostureEngine] = None,
        journal: Optional[Journal] = None,
        now_fn: Callable[[], float] = time.time,
        skill_bank: Optional[Any] = None,
        skill_extractor: Optional[SkillExtractor] = None,
        skill_governance_adapter: Optional[Any] = None,
        skill_auto_extract: bool = True,
        cognitive_router: Optional[Any] = None,
    ):
        self.agent = agent
        # Reuse the agent's own governor when available so policy packs
        # stay consistent between interactive calls and autonomous runs.
        self.governor = governor or getattr(agent, "governor", None) or SRGGovernor()
        self.planner = planner or Planner()
        self.verifier = verifier or Verifier()
        self.output_guard = output_guard or OutputGuard()
        self.posture_engine = posture_engine or PostureEngine(governor=self.governor)
        self.journal = journal or getattr(agent, "journal", None)
        self._now = now_fn
        self.skill_bank = skill_bank
        self.skill_extractor = skill_extractor or SkillExtractor()
        self.skill_governance_adapter = skill_governance_adapter
        self.skill_auto_extract = skill_auto_extract
        # Borrow the agent's cognitive router when available so autonomous
        # runs share the System 1/System 2 routing surface that interactive
        # turns already use. Observation-only here: the router gets to
        # SEE every autonomous goal (and update fingerprints / journal
        # decisions) without changing TriLoop's plan/execute/verify path.
        self.cognitive_router = cognitive_router or getattr(
            agent, "cognitive_router", None
        )

    # ------------------------------------------------------------------ run
    def run(
        self,
        goal: str,
        *,
        posture_bias: Optional[PostureName] = None,
        max_iterations: Optional[int] = None,
    ) -> TriLoopResult:
        """Execute the goal under SRG governance. Returns a full trace."""
        started = self._now()
        posture, pre_flight = self.posture_engine.select(goal, bias=posture_bias)
        self._journal("triloop.start", {
            "goal": _clip(goal, 500),
            "posture": posture.name,
            "posture_reasons": list(posture.reasons),
            "pre_flight_decision": pre_flight.decision,
            "pre_flight_risk": pre_flight.risk,
        })

        # Pre-flight hard-deny: SRG said no at the input-level. Don't even plan.
        if pre_flight.decision == "deny":
            return TriLoopResult(
                status="denied",
                goal=goal,
                posture=posture,
                pre_flight=pre_flight,
                total_duration_sec=self._now() - started,
            )

        # ---------- Cognitive routing (autonomous-mode observation) ------
        # If a cognitive router is wired in, ask it for a routing decision.
        # Observation-only: we journal the decision and stash it on the
        # result so the dashboard sees autonomous-path routes alongside
        # interactive ones. Plan/execute/verify is unchanged.
        routing_decision = None
        if self.cognitive_router is not None:
            try:
                routing_decision = self.cognitive_router.decide(
                    user_input=goal,
                    gov=pre_flight,
                    posture_name=posture.name,
                )
                self._journal("triloop.routing.decided", {
                    "system": getattr(routing_decision, "system", ""),
                    "fingerprint": getattr(routing_decision, "fingerprint", ""),
                    "reason": getattr(routing_decision, "reason", ""),
                    "risk": getattr(routing_decision, "risk", 0.0),
                    "skill_match": getattr(
                        routing_decision, "skill_match_name", ""
                    ) or "",
                })
            except Exception as exc:
                # Routing is informational; never let it break a run.
                self._journal("triloop.routing.error", {"error": str(exc)})

        max_iters = max_iterations if max_iterations is not None else (
            posture.max_replan_budget + 1  # 1 initial + N replans
        )

        iterations: List[IterationTrace] = []
        last_plan: Optional[Plan] = None
        last_failure_context = ""

        for i in range(1, max_iters + 1):
            # ---------- Plan ------------------------------------------------
            if i == 1 or last_plan is None:
                plan = self.planner.make_plan(goal)
            else:
                plan = self.planner.replan(last_plan, last_failure_context)
            trace = IterationTrace(iteration=i, plan_reasoning=plan.reasoning)
            self._journal("triloop.plan", {
                "iteration": i,
                "steps": len(plan.steps),
                "reasoning": _clip(plan.reasoning, 500),
            })

            # ---------- Plan review ----------------------------------------
            if posture.require_plan_review:
                plan_text = _serialize_plan_for_srg(plan)
                plan_gate = self.governor.evaluate(plan_text)
                if plan_gate.decision == "deny":
                    self._journal("triloop.plan.denied", {
                        "iteration": i,
                        "risk": plan_gate.risk,
                        "reasons": plan_gate.reasons,
                    })
                    trace.halted_reason = "plan-denied-by-srg"
                    iterations.append(trace)
                    return TriLoopResult(
                        status="plan_denied",
                        goal=goal,
                        posture=posture,
                        pre_flight=pre_flight,
                        iterations=iterations,
                        total_duration_sec=self._now() - started,
                        routing_decision=routing_decision,
                    )

            # ---------- Execute --------------------------------------------
            outputs: List[str] = []
            consec_failures = 0
            for step in _ordered(plan):
                step_trace, ok = self._execute_step(step, posture)
                trace.steps.append(step_trace)
                if ok:
                    outputs.append(step_trace.output)
                    consec_failures = 0
                else:
                    consec_failures += 1
                    if consec_failures >= posture.max_consecutive_failures:
                        trace.halted_reason = (
                            f"consecutive-failure-limit:{consec_failures}"
                        )
                        self._journal("triloop.halt", {
                            "iteration": i,
                            "reason": trace.halted_reason,
                        })
                        break

            # ---------- Verify ---------------------------------------------
            verdict = self.verifier.check(outputs, goal)
            trace.verify = verdict
            self._journal("triloop.verify", {
                "iteration": i,
                "status": verdict.status,
                "confidence": verdict.confidence,
                "summary": _clip(verdict.summary, 500),
            })
            iterations.append(trace)

            if verdict.passed:
                result = TriLoopResult(
                    status="passed",
                    goal=goal,
                    posture=posture,
                    pre_flight=pre_flight,
                    iterations=iterations,
                    final_outputs=outputs,
                    final_verdict=verdict,
                    successful_plan=plan,
                    total_duration_sec=self._now() - started,
                    routing_decision=routing_decision,
                )
                self._maybe_extract_skill(goal, plan, iterations)
                return result

            # Prepare for replan
            last_plan = plan
            last_failure_context = "\n".join([
                f"verdict: {verdict.status} (conf {verdict.confidence:.2f})",
                f"summary: {verdict.summary}",
                *[f"suggestion: {s}" for s in verdict.suggestions],
                *([f"halt: {trace.halted_reason}"] if trace.halted_reason else []),
            ])

            # Replan-budget check before the next iteration.
            if i - 1 >= posture.max_replan_budget:
                return TriLoopResult(
                    status="replan_budget_exhausted",
                    goal=goal,
                    posture=posture,
                    pre_flight=pre_flight,
                    iterations=iterations,
                    final_outputs=outputs,
                    final_verdict=verdict,
                    total_duration_sec=self._now() - started,
                    routing_decision=routing_decision,
                )

        # Loop bound exhausted without passing.
        last_iter = iterations[-1] if iterations else None
        return TriLoopResult(
            status="exhausted",
            goal=goal,
            posture=posture,
            pre_flight=pre_flight,
            iterations=iterations,
            final_outputs=(
                [s.output for s in last_iter.steps if s.output] if last_iter else []
            ),
            final_verdict=last_iter.verify if last_iter else None,
            total_duration_sec=self._now() - started,
            routing_decision=routing_decision,
        )

    # ------------------------------------------------------------- step
    def _execute_step(
        self, step: PlanStep, posture: Posture
    ) -> tuple[StepTrace, bool]:
        """Run one step end-to-end. Returns (trace, ok)."""
        started = self._now()
        step_gate = self.governor.evaluate(step.action)
        if step_gate.decision == "deny" or (
            step_gate.decision == "escalate" and posture.name == "conservative"
        ):
            # Conservative posture treats escalate as a halt point.
            trace = StepTrace(
                step_id=step.id,
                action=step.action,
                decision="deny" if step_gate.decision == "deny" else "escalate",
                srg_risk=step_gate.risk,
                reasons=list(step_gate.reasons),
                duration_sec=self._now() - started,
            )
            step.status = "failed"
            self._journal("triloop.step.denied", {
                "step_id": step.id,
                "srg_decision": step_gate.decision,
                "reasons": step_gate.reasons,
            })
            return trace, False

        # Execute via the agent.
        try:
            response = self.agent.think(step.action)
        except Exception as exc:  # pragma: no cover — defensive
            step.status = "failed"
            trace = StepTrace(
                step_id=step.id,
                action=step.action,
                decision="error",
                srg_risk=step_gate.risk,
                reasons=list(step_gate.reasons),
                error=f"{type(exc).__name__}: {exc}",
                duration_sec=self._now() - started,
            )
            self._journal("triloop.step.error", {
                "step_id": step.id,
                "error": trace.error,
            })
            return trace, False

        text = getattr(response, "text", "") or ""
        tool_calls = int(getattr(response, "tool_calls_made", 0) or 0)

        # Output gate.
        if posture.require_output_guard:
            guard: OutputGuardResult = self.output_guard.inspect(
                text, tool_calls_made=tool_calls
            )
        else:  # pragma: no cover — posture never disables output guard today
            guard = OutputGuardResult(decision="allow", reasons=["guard-skipped"])

        if guard.decision == "deny":
            step.status = "failed"
            trace = StepTrace(
                step_id=step.id,
                action=step.action,
                decision="output-denied",
                srg_risk=step_gate.risk,
                reasons=list(step_gate.reasons),
                output="",  # blocked outputs are never surfaced
                output_decision="deny",
                output_signals=guard.signal_count,
                tool_calls_made=tool_calls,
                duration_sec=self._now() - started,
                error=", ".join(guard.reasons[:3]),
            )
            self._journal("triloop.step.output_denied", {
                "step_id": step.id,
                "reasons": guard.reasons,
            })
            return trace, False

        safe_text = (
            guard.redacted_text if guard.decision == "redact" and guard.redacted_text
            else text
        )
        step.status = "done"
        step.result = safe_text
        trace = StepTrace(
            step_id=step.id,
            action=step.action,
            decision="executed",
            srg_risk=step_gate.risk,
            reasons=list(step_gate.reasons),
            output=safe_text,
            output_decision=guard.decision,
            output_signals=guard.signal_count,
            tool_calls_made=tool_calls,
            duration_sec=self._now() - started,
        )
        self._journal("triloop.step.ok", {
            "step_id": step.id,
            "output_decision": guard.decision,
            "output_signals": guard.signal_count,
            "tool_calls_made": tool_calls,
        })
        return trace, True

    def _maybe_extract_skill(
        self,
        goal: str,
        plan: Plan,
        iterations: List[IterationTrace],
    ) -> None:
        if not self.skill_auto_extract or self.skill_bank is None:
            return
        verify_summary = ""
        if iterations and iterations[-1].verify:
            verify_summary = iterations[-1].verify.summary or ""
        contract = self.skill_extractor.extract_from_trace(
            goal,
            plan.steps,
            plan.reasoning,
            task_id=f"triloop-{int(self._now())}",
            verify_summary=verify_summary,
        )
        if not contract:
            return
        if self.skill_governance_adapter is not None:
            gate = self.skill_governance_adapter.check_skill_promotion(contract)
            if not gate.allowed:
                self._journal("triloop.skill.extract_denied", {
                    "name": contract.name,
                    "reasons": gate.reasons,
                })
                return
        try:
            self.skill_bank.add(contract)
            self._journal("triloop.skill.extracted", {
                "skill_id": contract.skill_id,
                "name": contract.name,
            })
        except Exception as exc:  # pragma: no cover — persistence must not break loop
            self._journal("triloop.skill.extract_error", {"error": str(exc)})

    # --------------------------------------------------------- journal
    def _journal(self, kind: str, payload: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.write(kind, payload)
        except Exception:  # pragma: no cover — journaling must never crash the loop
            pass


# --------------------------------------------------------------- helpers
def _ordered(plan: Plan) -> List[PlanStep]:
    """Return plan steps in topological dependency order.

    Falls back to source order for any step whose dependencies can't be
    resolved — we still execute, we don't stall. The verifier will catch
    any consequent failures.
    """
    by_id = {s.id: s for s in plan.steps}
    visited: set[int] = set()
    ordered: List[PlanStep] = []

    def visit(s: PlanStep, stack: set[int]) -> None:
        if s.id in visited:
            return
        if s.id in stack:
            # Cycle — break by treating as already-visited; source order wins.
            return
        stack.add(s.id)
        for dep in s.depends_on:
            if dep in by_id:
                visit(by_id[dep], stack)
        stack.discard(s.id)
        visited.add(s.id)
        ordered.append(s)

    for s in plan.steps:
        visit(s, set())
    return ordered


def _serialize_plan_for_srg(plan: Plan) -> str:
    """Flatten a plan into a single string SRG can scan.

    We don't want to lose context when SRG evaluates the plan, so we include
    reasoning + every step's action + every tool_input. A deny-keyword
    hidden in a tool input must still trip the gate.
    """
    parts: List[str] = [f"goal: {plan.goal}", f"reasoning: {plan.reasoning}"]
    for s in plan.steps:
        parts.append(f"step {s.id}: {s.action}")
        if s.tool:
            parts.append(f"  tool: {s.tool}")
        if s.tool_input:
            parts.append(f"  input: {s.tool_input}")
    return "\n".join(parts)


def _clip(s: str, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[: n - 3] + "..."


__all__ = [
    "TriLoop",
    "TriLoopResult",
    "TriLoopStatus",
    "IterationTrace",
    "StepTrace",
]
