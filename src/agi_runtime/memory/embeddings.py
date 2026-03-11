"""Gemini Embedding 2 integration for semantic memory.

Uses Google's gemini-embedding-2 model to embed text (and optionally images)
into a unified vector space. This powers semantic search over the agent's
memory, identity evolution history, and journal events.

The embedding space is used by the ALE cache for intent-similarity matching
and by the identity engine for principle clustering.

Requires:
    pip install google-genai
    export GOOGLE_API_KEY=...
"""

from __future__ import annotations

import os
import json
import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

try:
    from google import genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


@dataclass
class EmbeddingEntry:
    text: str
    vector: List[float]
    metadata: dict = field(default_factory=dict)

    @property
    def text_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:16]


@dataclass
class SimilarityResult:
    text: str
    score: float
    metadata: dict


class GeminiEmbeddingStore:
    """Local embedding store powered by Google Gemini Embedding 2.

    Stores embeddings in a local JSON file for persistence.
    Uses gemini-embedding-2 for state-of-the-art multilingual,
    multimodal embedding with Matryoshka dimension flexibility.
    """

    MODEL = "gemini-embedding-2"
    DEFAULT_DIMENSIONS = 768  # Good balance of quality vs storage

    def __init__(
        self,
        store_path: str = "memory/embeddings.json",
        dimensions: int = DEFAULT_DIMENSIONS,
    ):
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.dimensions = dimensions
        self._entries: List[EmbeddingEntry] = []
        self._client = None
        self._load()

        if _GENAI_AVAILABLE and os.environ.get("GOOGLE_API_KEY"):
            self._client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    def _load(self):
        if self.store_path.exists():
            data = json.loads(self.store_path.read_text())
            self._entries = [EmbeddingEntry(**e) for e in data]

    def _save(self):
        self.store_path.write_text(
            json.dumps([asdict(e) for e in self._entries], indent=2)
        )

    @property
    def available(self) -> bool:
        return self._client is not None

    def embed_text(self, text: str) -> Optional[List[float]]:
        """Embed a single text string using Gemini Embedding 2.

        Returns the embedding vector, or None if the API is unavailable.
        Uses Matryoshka truncation to the configured dimensions.
        """
        if not self._client:
            return None

        result = self._client.models.embed_content(
            model=self.MODEL,
            contents=text,
            config={
                "output_dimensionality": self.dimensions,
            },
        )
        return result.embeddings[0].values

    def add(self, text: str, metadata: Optional[dict] = None) -> bool:
        """Embed and store a text entry. Returns True if successful."""
        vector = self.embed_text(text)
        if vector is None:
            return False

        # Deduplicate by text hash
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        self._entries = [e for e in self._entries if e.text_hash != text_hash]

        entry = EmbeddingEntry(
            text=text,
            vector=vector,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        self._save()
        return True

    def search(self, query: str, top_k: int = 5) -> List[SimilarityResult]:
        """Find the most similar stored entries to a query string.

        Uses cosine similarity over the Gemini Embedding 2 vectors.
        """
        query_vector = self.embed_text(query)
        if query_vector is None or not self._entries:
            return []

        scored = []
        for entry in self._entries:
            score = _cosine_similarity(query_vector, entry.vector)
            scored.append(SimilarityResult(
                text=entry.text,
                score=score,
                metadata=entry.metadata,
            ))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def count(self) -> int:
        return len(self._entries)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        # Truncate to shorter length (Matryoshka compatibility)
        min_len = min(len(a), len(b))
        a = a[:min_len]
        b = b[:min_len]

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
