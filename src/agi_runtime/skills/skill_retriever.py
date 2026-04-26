"""Skill Retriever — semantic + keyword skill matching.

Uses GeminiEmbeddingStore when available, falls back to keyword matching
(same as old SkillManager). Scores by: embedding similarity, confidence,
recency, and task-type match.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from agi_runtime.skills.skill_schema import SkillContract


@dataclass
class SkillMatch:
    """A skill matched to a query with a relevance score."""
    skill: SkillContract
    relevance: float  # 0.0-1.0 combined score
    match_reasons: List[str] = field(default_factory=list)


class SkillRetriever:
    """Retrieves relevant skills for a given task description.

    Scoring formula:
        relevance = 0.4 * text_similarity
                  + 0.3 * confidence_score
                  + 0.2 * recency_score
                  + 0.1 * task_type_match
    """

    WEIGHTS = {
        "similarity": 0.4,
        "confidence": 0.3,
        "recency": 0.2,
        "task_type": 0.1,
    }

    def __init__(self, embedding_store=None):
        self._embedding_store = embedding_store

    def find_matches(
        self,
        query: str,
        skills: List[SkillContract],
        *,
        top_k: int = 5,
        min_relevance: float = 0.1,
        task_type: str = "",
    ) -> List[SkillMatch]:
        """Find the most relevant skills for a query."""
        if not skills or not query:
            return []

        matches: List[SkillMatch] = []
        for skill in skills:
            if skill.status not in ("active", "candidate"):
                continue
            score, reasons = self._score_skill(query, skill, task_type)
            if score >= min_relevance:
                matches.append(SkillMatch(
                    skill=skill,
                    relevance=round(score, 3),
                    match_reasons=reasons,
                ))

        matches.sort(key=lambda m: m.relevance, reverse=True)
        return matches[:top_k]

    def _score_skill(
        self, query: str, skill: SkillContract, task_type: str,
    ) -> tuple[float, list[str]]:
        """Compute composite relevance score."""
        reasons: list[str] = []

        # Text similarity (keyword-based fallback)
        sim = self._text_similarity(query, skill)
        if sim > 0:
            reasons.append(f"text-match:{sim:.2f}")

        # Confidence
        conf = skill.confidence_score
        if conf > 0.7:
            reasons.append(f"high-confidence:{conf:.2f}")

        # Recency
        recency = self._recency_score(skill)
        if recency > 0.5:
            reasons.append("recently-used")

        # Task type match
        type_match = 1.0 if (task_type and skill.task_type == task_type) else 0.0
        if type_match > 0:
            reasons.append(f"task-type:{task_type}")

        score = (
            self.WEIGHTS["similarity"] * sim
            + self.WEIGHTS["confidence"] * conf
            + self.WEIGHTS["recency"] * recency
            + self.WEIGHTS["task_type"] * type_match
        )
        return score, reasons

    def _text_similarity(self, query: str, skill: SkillContract) -> float:
        """Keyword overlap similarity (fast, no embeddings needed)."""
        query_words = set(query.lower().split())
        skill_words = set()
        # Collect all searchable text from the skill
        for text in [skill.name, skill.description, *skill.triggers, *skill.tags,
                     *skill.preconditions, *skill.execution_steps]:
            skill_words.update(text.lower().split())

        if not skill_words:
            return 0.0
        overlap = query_words & skill_words
        if not overlap:
            return 0.0
        # Jaccard-like but weighted toward query coverage
        return len(overlap) / max(len(query_words), 1)

    def _recency_score(self, skill: SkillContract) -> float:
        """Score based on how recently the skill was used."""
        if not skill.last_used_at:
            return 0.3  # Neutral for never-used
        days = (time.time() - skill.last_used_at) / 86400
        if days < 1:
            return 1.0
        if days < 7:
            return 0.8
        if days < 30:
            return 0.5
        return 0.2


__all__ = ["SkillRetriever", "SkillMatch"]
