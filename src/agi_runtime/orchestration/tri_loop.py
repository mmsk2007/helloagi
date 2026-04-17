"""Plan → Execute → Verify loop with re-planning on failure.

The TriLoop is HelloAGI's closed-loop goal pursuit system.
On PARTIAL/FAIL, it re-plans with failure context and retries.
"""

from dataclasses import dataclass
from agi_runtime.planner.planner import Planner
from agi_runtime.executor.executor import Executor
from agi_runtime.verifier.verifier import Verifier


@dataclass
class LoopResult:
    ok: bool
    summary: str
    attempts: int = 1
    plan_steps: int = 0
    exec_outputs: int = 0


class TriLoop:
    MAX_RETRIES = 2  # Max re-planning attempts

    def __init__(self):
        self.planner = Planner()
        self.executor = Executor()
        self.verifier = Verifier()

    def run(self, goal: str) -> LoopResult:
        """Run the Plan → Execute → Verify loop with re-planning."""
        plan = self.planner.make_plan(goal)

        for attempt in range(1, self.MAX_RETRIES + 2):
            # Execute
            exec_result = self.executor.run(plan)

            # Collect output strings for verifier
            output_strings = [sr.output for sr in exec_result.outputs]

            # Verify
            verify = self.verifier.check(output_strings, goal)

            if verify.passed:
                return LoopResult(
                    ok=True,
                    summary=verify.summary,
                    attempts=attempt,
                    plan_steps=len(plan.steps),
                    exec_outputs=len(exec_result.outputs),
                )

            # FAIL or PARTIAL — re-plan if we have retries left
            if attempt <= self.MAX_RETRIES:
                failure_context = (
                    f"Attempt {attempt} result: {verify.status}\n"
                    f"Summary: {verify.summary}\n"
                    f"Suggestions: {'; '.join(verify.suggestions)}\n"
                    f"Failed outputs: {[sr.output[:100] for sr in exec_result.failed_steps]}"
                )
                plan = self.planner.replan(plan, failure_context)

        # All retries exhausted
        return LoopResult(
            ok=False,
            summary=f"Failed after {self.MAX_RETRIES + 1} attempts: {verify.summary}",
            attempts=self.MAX_RETRIES + 1,
            plan_steps=len(plan.steps),
            exec_outputs=len(exec_result.outputs),
        )
