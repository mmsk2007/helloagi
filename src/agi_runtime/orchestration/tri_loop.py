from dataclasses import dataclass
from agi_runtime.planner.planner import Planner
from agi_runtime.executor.executor import Executor
from agi_runtime.verifier.verifier import Verifier


@dataclass
class LoopResult:
    ok: bool
    summary: str


class TriLoop:
    def __init__(self):
        self.planner = Planner()
        self.executor = Executor()
        self.verifier = Verifier()

    def run(self, goal: str) -> LoopResult:
        plan = self.planner.make_plan(goal)
        exec_result = self.executor.run(plan.steps)
        verify = self.verifier.check(exec_result.outputs, goal)
        return LoopResult(ok=verify.passed, summary=verify.summary)
