from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional
import time


@dataclass
class PrecomputeEntry:
    value: str
    ts: float


@dataclass
class ALEngine:
    """Tiny anticipatory cache to reduce response latency."""

    ttl_seconds: int = 600
    cache: Dict[str, PrecomputeEntry] = field(default_factory=dict)

    def key_for(self, text: str) -> str:
        t = text.strip().lower()
        if "build" in t and "agent" in t:
            return "intent:build-agent"
        if "market" in t or "x " in t or "twitter" in t:
            return "intent:growth"
        return "intent:general"

    def get(self, text: str) -> str | None:
        k = self.key_for(text)
        e = self.cache.get(k)
        if not e:
            return None
        if time.time() - e.ts > self.ttl_seconds:
            self.cache.pop(k, None)
            return None
        return e.value

    def put(self, text: str, value: str):
        self.cache[self.key_for(text)] = PrecomputeEntry(value=value, ts=time.time())
