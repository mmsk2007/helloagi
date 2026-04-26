"""Structured rolling context — scores segments and fits a token budget."""

from __future__ import annotations

from typing import Any, Dict, List

from agi_runtime.context.context_segment import ContextSegment
from agi_runtime.context.memory_selector import sort_by_relevance


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class ContextManager:
    """Assembles a bounded supplement for the system prompt."""

    def __init__(self, settings: Dict[str, Any] | None = None):
        cfg = settings if isinstance(settings, dict) else {}
        self.managed = bool(cfg.get("managed", True))
        self.max_budget_tokens = int(cfg.get("max_budget_tokens", 120000))

    def build_supplement(
        self,
        *,
        query_hint: str,
        segments: List[ContextSegment],
    ) -> str:
        if not self.managed or not segments:
            return ""
        ranked = sort_by_relevance(segments, query_hint)
        budget = min(self.max_budget_tokens, 8000)  # practical cap for supplement
        used = 0
        parts: List[str] = []
        for seg in ranked:
            cost = min(seg.max_tokens, _approx_tokens(seg.content))
            max_chars = max(4, cost * 4)
            chunk = seg.content[:max_chars]
            chunk_cost = min(cost, _approx_tokens(chunk))
            if used + chunk_cost > budget:
                remain = max(0, budget - used)
                if remain < 50:
                    break
                clip = seg.content[: max(4, remain * 4)]
                parts.append(f"[{seg.kind}]\n{clip}\n")
                break
            parts.append(f"[{seg.kind}]\n{chunk}\n")
            used += chunk_cost
        if not parts:
            return ""
        return "Structured context (rolled):\n" + "\n".join(parts).strip()
