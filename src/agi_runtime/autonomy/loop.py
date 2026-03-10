import time
from agi_runtime.core.agent import HelloAGIAgent


class AutonomousLoop:
    def __init__(self, agent: HelloAGIAgent, goal: str, interval_sec: int = 60):
        self.agent = agent
        self.goal = goal
        self.interval_sec = interval_sec

    def run_steps(self, steps: int = 3):
        outputs = []
        for i in range(steps):
            q = f"Autonomous step {i+1}: progress toward goal: {self.goal}"
            outputs.append(self.agent.think(q))
            time.sleep(0.01)
        return outputs
