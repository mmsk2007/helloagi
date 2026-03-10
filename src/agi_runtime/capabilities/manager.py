from dataclasses import dataclass, field
from typing import Dict, Set


@dataclass
class CapabilityManager:
    grants: Dict[str, Set[str]] = field(default_factory=dict)

    def grant(self, agent_id: str, capability: str):
        self.grants.setdefault(agent_id, set()).add(capability)

    def has(self, agent_id: str, capability: str) -> bool:
        return capability in self.grants.get(agent_id, set())
