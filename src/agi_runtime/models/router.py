"""Multi-provider model routing with tier heuristics.

Selects a tier (speed | balanced | quality) from the user prompt, then maps
that tier to a concrete model id per backbone provider (Anthropic, OpenAI).
Google Gemini continues to use ``agi_runtime.models.gemini_router`` in the
Gemini-specific code paths.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List


@dataclass
class RouteDecision:
    tier: str  # speed | balanced | quality
    model: str  # actual model ID for the active provider
    reason: str


# Anthropic catalog (Claude IDs)
ANTHROPIC_MODELS: dict[str, dict[str, List[str]]] = {
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


def _openai_model_for_tier(tier: str) -> str:
    """Resolve OpenAI model id for a tier (env overrides per plan)."""
    defaults = {
        "speed": "gpt-4o-mini",
        "balanced": "gpt-4o",
        "quality": "gpt-4o",
    }
    env_keys = {
        "speed": "HELLOAGI_OPENAI_MODEL_SPEED",
        "balanced": "HELLOAGI_OPENAI_MODEL_BALANCED",
        "quality": "HELLOAGI_OPENAI_MODEL_QUALITY",
    }
    key = env_keys.get(tier, "HELLOAGI_OPENAI_MODEL_BALANCED")
    return (os.environ.get(key) or "").strip() or defaults.get(tier, defaults["balanced"])


def pick_tier(prompt: str) -> tuple[str, str]:
    """Return (tier, reason) from heuristics."""
    p = (prompt or "").lower()
    if any(k in p for k in SPEED_KEYWORDS) and len(prompt) < 100:
        return "speed", "latency-priority"
    if any(k in p for k in QUALITY_KEYWORDS):
        return "quality", "depth-priority"
    if len(prompt) > 500:
        return "quality", "long-prompt"
    return "balanced", "default"


def route_for_provider(provider: str, prompt: str) -> RouteDecision:
    """Pick tier + concrete model for ``anthropic`` or ``openai``."""
    tier, reason = pick_tier(prompt or "")
    prov = (provider or "anthropic").strip().lower()
    if prov == "openai":
        return RouteDecision(tier=tier, model=_openai_model_for_tier(tier), reason=reason)
    catalog = ANTHROPIC_MODELS
    model = catalog.get(tier, catalog["balanced"])["primary"]
    return RouteDecision(tier=tier, model=model, reason=reason)


def model_id_for_tier(provider: str, tier: str) -> str:
    """Force a tier without re-running keyword heuristics (e.g. default_model_tier)."""
    prov = (provider or "anthropic").strip().lower()
    tier = (tier or "balanced").strip().lower()
    if tier not in ("speed", "balanced", "quality"):
        tier = "balanced"
    if prov == "openai":
        return _openai_model_for_tier(tier)
    return ANTHROPIC_MODELS.get(tier, ANTHROPIC_MODELS["balanced"])["primary"]


class ModelRouter:
    """Route to the optimal model based on task complexity (Anthropic default)."""

    def route(self, prompt: str) -> RouteDecision:
        return route_for_provider("anthropic", prompt)

    def get_model(self, tier: str) -> str:
        return model_id_for_tier("anthropic", tier)

    def get_fallbacks(self, tier: str) -> List[str]:
        return list(ANTHROPIC_MODELS.get(tier, ANTHROPIC_MODELS["balanced"])["fallback"])


# Back-compat for imports of MODELS
MODELS = ANTHROPIC_MODELS
