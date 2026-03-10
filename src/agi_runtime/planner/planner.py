from dataclasses import dataclass


@dataclass
class Plan:
    goal: str
    steps: list[str]


class Planner:
    def make_plan(self, goal: str) -> Plan:
        steps = [
            "Clarify outcome and success metric",
            "Map constraints and risks",
            "Execute smallest high-leverage action",
            "Verify result against metric",
        ]
        return Plan(goal=goal, steps=steps)
