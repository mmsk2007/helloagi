from dataclasses import dataclass, field
from typing import Dict


@dataclass
class AgentSpec:
    id: str
    name: str
    goal: str


@dataclass
class AgentRegistry:
    agents: Dict[str, AgentSpec] = field(default_factory=dict)

    def register(self, spec: AgentSpec):
        self.agents[spec.id] = spec

    def get(self, agent_id: str) -> AgentSpec | None:
        return self.agents.get(agent_id)

    def list_ids(self) -> list[str]:
        return sorted(self.agents.keys())
