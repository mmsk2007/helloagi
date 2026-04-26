"""Heuristic relevance scoring for memory/context segments (MVP, no embeddings)."""

from __future__ import annotations

from typing import Iterable

from agi_runtime.context.context_segment import ContextSegment


def score_segment(query_words: set[str], segment: ContextSegment) -> float:
    """Boost segments whose words overlap the active query."""
    if not query_words or not segment.content:
        return segment.relevance_score
    body = set(segment.content.lower().split())
    overlap = len(query_words & body)
    if overlap == 0:
        return segment.relevance_score
    boost = min(0.4, overlap / max(len(query_words), 1))
    return min(1.0, segment.relevance_score + boost)


def sort_by_relevance(
    segments: Iterable[ContextSegment],
    query: str,
) -> list[ContextSegment]:
    qw = {w for w in query.lower().split() if len(w) > 2}
    ranked = sorted(
        segments,
        key=lambda s: (score_segment(qw, s), s.priority),
        reverse=True,
    )
    return ranked
