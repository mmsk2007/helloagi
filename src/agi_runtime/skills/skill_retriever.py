"""Skill Retriever — semantic + keyword skill matching.

Uses GeminiEmbeddingStore when available: embeds the query once and compares
to cached per-skill text embeddings (COS-PLAY-style retrieval at scale).
Falls back to keyword Jaccard-style overlap when embeddings are unavailable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from agi_runtime.memory.embeddings import cosine_similarity_vectors
from agi_runtime.skills.skill_schema import SkillContract


@dataclass
class SkillMatch:
    """A skill matched to a query with a relevance score."""
    skill: SkillContract
    relevance: float  # 0.0-1.0 combined score
    match_reasons: List[str] = field(default_factory=list)


class SkillRetriever:
    """Retrieves relevant skills for a given task description.

    Scoring formula (embedding path, when Gemini store is live):
        relevance ≈ 0.22 * keyword_similarity
                    + 0.38 * embedding_cosine
                    + 0.25 * confidence_score
                    + 0.15 * recency_score

    Keyword-only fallback keeps the previous blend (similarity-heavy).
    """

    WEIGHTS_EMBED = {
        "similarity": 0.22,
        "embedding": 0.38,
        "confidence": 0.25,
        "recency": 0.15,
        "task_type": 0.0,
    }
    WEIGHTS_KEYWORD = {
        "similarity": 0.4,
        "embedding": 0.0,
        "confidence": 0.3,
        "recency": 0.2,
        "task_type": 0.1,
    }

    def __init__(self, embedding_store=None):
        self._embedding_store = embedding_store
        self._skill_vec_cache: Dict[str, List[float]] = {}

    def bind_embedding_store(self, embedding_store) -> None:
        """Attach or clear the embedding backend (called from HelloAGIAgent each turn)."""
        if embedding_store is not self._embedding_store:
            self._embedding_store = embedding_store
            self._skill_vec_cache.clear()

    def invalidate_embedding_cache(self, *skill_ids: str) -> None:
        """Drop cached vectors after merge/split/version bumps."""
        if not skill_ids:
            return
        for key in list(self._skill_vec_cache.keys()):
            if any(key.startswith(f"{sid}:") for sid in skill_ids if sid):
                self._skill_vec_cache.pop(key, None)

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

        store = self._embedding_store
        query_vec: Optional[List[float]] = None
        if store is not None and getattr(store, "available", False):
            try:
                query_vec = store.embed_text(query)
            except Exception:
                query_vec = None

        matches: List[SkillMatch] = []
        for skill in skills:
            if skill.status not in ("active", "candidate"):
                continue
            score, reasons = self._score_skill(query, skill, task_type, query_vec=query_vec)
            if score >= min_relevance:
                matches.append(SkillMatch(
                    skill=skill,
                    relevance=round(score, 3),
                    match_reasons=reasons,
                ))

        matches.sort(key=lambda m: m.relevance, reverse=True)
        return matches[:top_k]

    def _skill_embedding_key(self, skill: SkillContract) -> str:
        return f"{skill.skill_id}:{skill.version}"

    def _embed_text_for_skill(self, skill: SkillContract) -> str:
        parts = [skill.name, skill.description, *skill.triggers[:8], *skill.tags[:6]]
        parts.extend(skill.preconditions[:5])
        parts.extend(skill.execution_steps[:12])
        return "\n".join(p for p in parts if (p or "").strip())[:8000]

    def _skill_embedding_vector(self, skill: SkillContract) -> Optional[List[float]]:
        store = self._embedding_store
        if store is None or not getattr(store, "available", False):
            return None
        key = self._skill_embedding_key(skill)
        cached = self._skill_vec_cache.get(key)
        if cached is not None:
            return cached
        text = self._embed_text_for_skill(skill)
        if not text.strip():
            return None
        try:
            vec = store.embed_text(text)
        except Exception:
            vec = None
        if vec:
            self._skill_vec_cache[key] = vec
        return vec

    def _score_skill(
        self,
        query: str,
        skill: SkillContract,
        task_type: str,
        *,
        query_vec: Optional[List[float]] = None,
    ) -> tuple[float, list[str]]:
        """Compute composite relevance score."""
        reasons: list[str] = []

        sim = self._text_similarity(query, skill)
        if sim > 0:
            reasons.append(f"text-match:{sim:.2f}")

        conf = skill.confidence_score
        if conf > 0.7:
            reasons.append(f"high-confidence:{conf:.2f}")

        recency = self._recency_score(skill)
        if recency > 0.5:
            reasons.append("recently-used")

        type_match = 1.0 if (task_type and skill.task_type == task_type) else 0.0
        if type_match > 0:
            reasons.append(f"task-type:{task_type}")

        embed_sim = 0.0
        if query_vec:
            sk_vec = self._skill_embedding_vector(skill)
            if sk_vec:
                embed_sim = max(0.0, min(1.0, cosine_similarity_vectors(query_vec, sk_vec)))
                reasons.append(f"embedding:{embed_sim:.2f}")

        if embed_sim > 0.0:
            w = self.WEIGHTS_EMBED
            score = (
                w["similarity"] * sim
                + w["embedding"] * embed_sim
                + w["confidence"] * conf
                + w["recency"] * recency
                + w["task_type"] * type_match
            )
        else:
            w = self.WEIGHTS_KEYWORD
            score = (
                w["similarity"] * sim
                + w["confidence"] * conf
                + w["recency"] * recency
                + w["task_type"] * type_match
            )
        return score, reasons

    def _text_similarity(self, query: str, skill: SkillContract) -> float:
        """Keyword overlap similarity (fast, no embeddings needed)."""
        query_words = set(query.lower().split())
        skill_words: set[str] = set()
        for text in [skill.name, skill.description, *skill.triggers, *skill.tags,
                     *skill.preconditions, *skill.execution_steps]:
            skill_words.update(text.lower().split())

        if not skill_words:
            return 0.0
        overlap = query_words & skill_words
        if not overlap:
            return 0.0
        return len(overlap) / max(len(query_words), 1)

    def _recency_score(self, skill: SkillContract) -> float:
        """Score based on how recently the skill was used."""
        if not skill.last_used_at:
            return 0.3
        days = (time.time() - skill.last_used_at) / 86400
        if days < 1:
            return 1.0
        if days < 7:
            return 0.8
        if days < 30:
            return 0.5
        return 0.2


__all__ = ["SkillRetriever", "SkillMatch"]
