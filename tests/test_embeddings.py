import unittest
from unittest.mock import patch, MagicMock
from agi_runtime.memory.embeddings import (
    GeminiEmbeddingStore,
    _cosine_similarity,
    EmbeddingEntry,
)


class TestCosineSimilarity(unittest.TestCase):
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(_cosine_similarity(v, v), 1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        self.assertAlmostEqual(_cosine_similarity(a, b), 0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        self.assertAlmostEqual(_cosine_similarity(a, b), -1.0)

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 1.0]
        self.assertEqual(_cosine_similarity(a, b), 0.0)

    def test_matryoshka_truncation(self):
        a = [1.0, 0.5, 0.3, 0.1]
        b = [1.0, 0.5]
        score = _cosine_similarity(a, b)
        self.assertGreater(score, 0.0)


class TestEmbeddingEntry(unittest.TestCase):
    def test_text_hash_deterministic(self):
        e = EmbeddingEntry(text="hello", vector=[1.0])
        self.assertEqual(e.text_hash, e.text_hash)
        self.assertEqual(len(e.text_hash), 16)

    def test_different_text_different_hash(self):
        e1 = EmbeddingEntry(text="hello", vector=[1.0])
        e2 = EmbeddingEntry(text="world", vector=[1.0])
        self.assertNotEqual(e1.text_hash, e2.text_hash)


class TestGeminiEmbeddingStoreOffline(unittest.TestCase):
    def test_unavailable_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            store = GeminiEmbeddingStore(store_path="/tmp/test_embed.json")
            self.assertFalse(store.available)

    def test_embed_returns_none_when_unavailable(self):
        with patch.dict("os.environ", {}, clear=True):
            store = GeminiEmbeddingStore(store_path="/tmp/test_embed.json")
            self.assertIsNone(store.embed_text("test"))

    def test_search_returns_empty_when_unavailable(self):
        with patch.dict("os.environ", {}, clear=True):
            store = GeminiEmbeddingStore(store_path="/tmp/test_embed.json")
            self.assertEqual(store.search("test"), [])

    def test_add_returns_false_when_unavailable(self):
        with patch.dict("os.environ", {}, clear=True):
            store = GeminiEmbeddingStore(store_path="/tmp/test_embed.json")
            self.assertFalse(store.add("test"))


if __name__ == "__main__":
    unittest.main()
