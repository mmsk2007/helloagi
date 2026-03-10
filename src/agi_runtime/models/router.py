from dataclasses import dataclass


@dataclass
class RouteDecision:
    tier: str  # speed | balanced | quality
    reason: str


class ModelRouter:
    def route(self, prompt: str) -> RouteDecision:
        p = prompt.lower()
        if any(k in p for k in ["urgent", "quick", "fast"]):
            return RouteDecision("speed", "latency-priority")
        if any(k in p for k in ["research", "strategy", "complex", "architecture"]):
            return RouteDecision("quality", "depth-priority")
        return RouteDecision("balanced", "default")
