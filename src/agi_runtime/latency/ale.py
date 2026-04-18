from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict


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
        """Cache key must be unique per utterance.

        Previously, almost everything mapped to ``intent:general``, so the first
        reply was replayed for every later message until TTL expired.
        """
        t = text.strip().lower()
        digest = hashlib.sha256(t.encode("utf-8", errors="replace")).hexdigest()[:24]
        if "build" in t and "agent" in t:
            return f"intent:build-agent:{digest}"
        if "market" in t or "x " in t or "twitter" in t:
            return f"intent:growth:{digest}"
        return f"intent:general:{digest}"

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
