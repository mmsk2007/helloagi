from dataclasses import dataclass
from agi_runtime.core.agent import HelloAGIAgent


@dataclass
class RuntimeConfig:
    goal: str
    mission: str = "Build useful intelligence that helps people create value"
    style: str = "direct, strategic, practical"
    domain_focus: str = "agents, automation, products"


class HelloAGIRuntime:
    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.agent = HelloAGIAgent()

    def step(self, user_input: str):
        return self.agent.think(user_input)
