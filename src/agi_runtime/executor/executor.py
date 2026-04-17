"""Real task executor with retry logic and failure recovery.

Executes plan steps using the tool system. Every tool call
passes through SRG governance before execution.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from agi_runtime.planner.planner import Plan, PlanStep
from agi_runtime.tools.registry import ToolRegistry, ToolResult
from agi_runtime.governance.srg import SRGGovernor
from agi_runtime.observability.journal import Journal


@dataclass
class StepResult:
    step_id: int
    ok: bool
    output: str
    attempts: int = 1
    duration_ms: float = 0


@dataclass
class ExecResult:
    ok: bool
    outputs: List[StepResult]
    total_duration_ms: float = 0

    @property
    def failed_steps(self) -> List[StepResult]:
        return [o for o in self.outputs if not o.ok]

    @property
    def summary(self) -> str:
        passed = sum(1 for o in self.outputs if o.ok)
        failed = sum(1 for o in self.outputs if not o.ok)
        return f"{passed} passed, {failed} failed, {self.total_duration_ms:.0f}ms total"


class Executor:
    """Execute plan steps using the tool system with retries."""

    MAX_RETRIES = 3
    RETRY_BACKOFF = [1.0, 2.0, 4.0]  # exponential backoff seconds

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        governor: SRGGovernor | None = None,
        journal: Journal | None = None,
    ):
        self.tools = tool_registry or ToolRegistry.get_instance()
        self.governor = governor or SRGGovernor()
        self.journal = journal

    def run(self, steps: list[str] | Plan) -> ExecResult:
        """Synchronous wrapper for async execution."""
        if isinstance(steps, list):
            # Legacy compatibility: list of step strings
            plan = Plan(
                goal="execute steps",
                steps=[PlanStep(id=i+1, action=s) for i, s in enumerate(steps)],
            )
        else:
            plan = steps

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._run_plan(plan))
                return future.result()
        return asyncio.run(self._run_plan(plan))

    async def _run_plan(self, plan: Plan) -> ExecResult:
        """Execute a plan respecting step dependencies."""
        start = time.time()
        results: List[StepResult] = []

        while not plan.is_complete:
            ready = plan.ready_steps
            if not ready:
                # No steps can proceed — deadlock or all failed
                break

            # Execute ready steps (could be parallel if independent)
            for step in ready:
                step.status = "running"
                step_result = await self._execute_step(step)
                results.append(step_result)

                if step_result.ok:
                    step.status = "done"
                    step.result = step_result.output
                else:
                    step.status = "failed"
                    step.result = step_result.output

        total_ms = (time.time() - start) * 1000
        all_ok = all(r.ok for r in results)

        return ExecResult(ok=all_ok, outputs=results, total_duration_ms=total_ms)

    async def _execute_step(self, step: PlanStep) -> StepResult:
        """Execute a single step with retries."""
        start = time.time()

        for attempt in range(self.MAX_RETRIES):
            if step.tool:
                # Execute via tool system
                tool_input = step.tool_input or {}

                # SRG governance gate
                tool_def = self.tools.get(step.tool)
                tool_risk = tool_def.risk.value if tool_def else "medium"
                gov = self.governor.evaluate_tool(step.tool, tool_input, tool_risk)

                if gov.decision == "deny":
                    return StepResult(
                        step_id=step.id,
                        ok=False,
                        output=f"SRG blocked: {'; '.join(gov.reasons)}",
                        attempts=attempt + 1,
                        duration_ms=(time.time() - start) * 1000,
                    )

                result = await self.tools.execute(step.tool, tool_input)

                if self.journal:
                    self.journal.write("executor_step", {
                        "step_id": step.id,
                        "tool": step.tool,
                        "attempt": attempt + 1,
                        "ok": result.ok,
                        "output_preview": result.to_content()[:200],
                    })

                if result.ok:
                    return StepResult(
                        step_id=step.id,
                        ok=True,
                        output=result.to_content(),
                        attempts=attempt + 1,
                        duration_ms=(time.time() - start) * 1000,
                    )

                # Retry with backoff
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF[attempt])
            else:
                # No tool — this is a reasoning/planning step, auto-pass
                return StepResult(
                    step_id=step.id,
                    ok=True,
                    output=f"Completed: {step.action}",
                    attempts=1,
                    duration_ms=(time.time() - start) * 1000,
                )

        # All retries exhausted
        return StepResult(
            step_id=step.id,
            ok=False,
            output=f"Failed after {self.MAX_RETRIES} attempts: {step.action}",
            attempts=self.MAX_RETRIES,
            duration_ms=(time.time() - start) * 1000,
        )
