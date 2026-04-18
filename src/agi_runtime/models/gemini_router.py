"""Pick a Gemini model id from prompt heuristics (mirrors ModelRouter tiers).

Uses Gemini 3.x preview ids from the Developer API. Preview names can change;
see https://ai.google.dev/gemini-api/docs/models — on 404 we fall back to stable 2.5 Flash.
"""

from __future__ import annotations

from dataclasses import dataclass

# Gemini 3.x (preview) — latest Flash-class routing per Google AI docs / changelog.
GEMINI_3_FLASH = "gemini-3-flash-preview"
GEMINI_31_FLASH_LITE = "gemini-3.1-flash-lite-preview"
GEMINI_31_PRO = "gemini-3.1-pro-preview"

# Stable fallback if a preview id is unavailable for the account or region.
GEMINI_FALLBACK_STABLE = "gemini-2.5-flash"

FLASH_FAST = GEMINI_31_FLASH_LITE
FLASH_DEFAULT = GEMINI_3_FLASH
FLASH_QUALITY = GEMINI_31_PRO


SPEED_KEYWORDS = ["urgent", "quick", "fast", "simple", "brief", "short", "ping", "hello", "hi"]
QUALITY_KEYWORDS = [
    "research", "strategy", "complex", "architecture", "analyze", "deep",
    "comprehensive", "detailed", "plan", "design", "review", "audit",
    "compare", "evaluate", "critique",
]


@dataclass
class GeminiRouteDecision:
    model: str
    reason: str


def route_gemini_model(prompt: str) -> GeminiRouteDecision:
    p = prompt.lower()
    if any(k in p for k in SPEED_KEYWORDS) and len(prompt) < 100:
        return GeminiRouteDecision(model=FLASH_FAST, reason="latency-priority")
    if any(k in p for k in QUALITY_KEYWORDS) or len(prompt) > 500:
        return GeminiRouteDecision(model=FLASH_QUALITY, reason="depth-or-long-prompt")
    return GeminiRouteDecision(model=FLASH_DEFAULT, reason="default")
