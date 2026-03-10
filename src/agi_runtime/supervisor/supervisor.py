from dataclasses import dataclass, field


@dataclass
class Supervisor:
    failures: dict[str, int] = field(default_factory=dict)

    def record_failure(self, agent_id: str):
        self.failures[agent_id] = self.failures.get(agent_id, 0) + 1

    def should_pause(self, agent_id: str, threshold: int = 3) -> bool:
        return self.failures.get(agent_id, 0) >= threshold
