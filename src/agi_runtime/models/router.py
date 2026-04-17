"""Multi-model router with intelligent tier selection and fallback chains.

Routes requests to the optimal model based on task complexity:
- Speed tier: Claude Haiku — fast tasks, compression, tool result processing
- Balanced tier: Claude Sonnet — most interactions
- Quality tier: Claude Opus — complex planning, analysis, code generation
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class RouteDecision:
    tier: str  # speed | balanced | quality
    model: str  # actual model ID
    reason: str


# Model catalog
MODELS = {
    "speed": {
        "primary": "claude-haiku-4-5-20251001",
        "fallback": ["claude-haiku-4-5-20251001"],
    },
    "balanced": {
        "primary": "claude-sonnet-4-6-20250514",
        "fallback": ["claude-sonnet-4-6-20250514", "claude-haiku-4-5-20251001"],
    },
    "quality": {
        "primary": "claude-sonnet-4-6-20250514",
        "fallback": ["claude-sonnet-4-6-20250514", "claude-haiku-4-5-20251001"],
    },
}

# Keywords that indicate task complexity
SPEED_KEYWORDS = ["urgent", "quick", "fast", "simple", "brief", "short", "ping", "hello", "hi"]
QUALITY_KEYWORDS = [
    "research", "strategy", "complex", "architecture", "analyze", "deep",
    "comprehensive", "detailed", "plan", "design", "review", "audit",
    "compare", "evaluate", "critique",
]


class ModelRouter:
    """Route to the optimal model based on task complexity."""

    def route(self, prompt: str) -> RouteDecision:
        """Select the best model tier for the given prompt."""
        p = prompt.lower()

        # Check for speed keywords
        if any(k in p for k in SPEED_KEYWORDS) and len(prompt) < 100:
            tier = "speed"
            reason = "latency-priority"
        # Check for quality keywords
        elif any(k in p for k in QUALITY_KEYWORDS):
            tier = "quality"
            reason = "depth-priority"
        # Long prompts get quality tier
        elif len(prompt) > 500:
            tier = "quality"
            reason = "long-prompt"
        else:
            tier = "balanced"
            reason = "default"

        model = MODELS[tier]["primary"]
        return RouteDecision(tier=tier, model=model, reason=reason)

    def get_model(self, tier: str) -> str:
        """Get the primary model for a given tier."""
        return MODELS.get(tier, MODELS["balanced"])["primary"]

    def get_fallbacks(self, tier: str) -> List[str]:
        """Get fallback models for a given tier."""
        return MODELS.get(tier, MODELS["balanced"])["fallback"]
