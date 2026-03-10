from dataclasses import dataclass, field


@dataclass
class MeteringEngine:
    counters: dict[str, int] = field(default_factory=dict)

    def add(self, key: str, amount: int = 1):
        self.counters[key] = self.counters.get(key, 0) + amount

    def get(self, key: str) -> int:
        return self.counters.get(key, 0)
