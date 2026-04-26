from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal

SegmentType = Literal[
    "task",
    "session",
    "memory",
    "tools_history",
    "skills",
    "preferences",
    "constraints",
    "srg",
]


@dataclass
class ContextSegment:
    """One typed slice of prompt context with a soft token budget."""

    kind: SegmentType
    priority: int  # higher = keep longer when trimming
    content: str
    max_tokens: int = 2000
    relevance_score: float = 0.5
    tags: List[str] = field(default_factory=list)
