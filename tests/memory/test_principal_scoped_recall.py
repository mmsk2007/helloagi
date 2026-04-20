from agi_runtime.memory.embeddings import EmbeddingEntry, GeminiEmbeddingStore


def _store_with_entries(tmp_path):
    store = GeminiEmbeddingStore(store_path=str(tmp_path / "embeddings.json"))
    store._entries = [
        EmbeddingEntry(text="legacy entry", vector=[1.0, 0.0], metadata={"category": "fact"}),
        EmbeddingEntry(
            text="alice entry",
            vector=[0.9, 0.1],
            metadata={"category": "fact", "principal_id": "alice"},
        ),
        EmbeddingEntry(
            text="bob entry",
            vector=[0.1, 0.9],
            metadata={"category": "fact", "principal_id": "bob"},
        ),
    ]
    store.embed_text = lambda _: [1.0, 0.0]
    return store


def test_search_compat_mode_includes_legacy_and_principal(tmp_path):
    store = _store_with_entries(tmp_path)
    results = store.search("hello", top_k=10, principal_id="alice", scope="compat")
    texts = [r.text for r in results]
    assert "alice entry" in texts
    assert "legacy entry" in texts
    assert "bob entry" not in texts


def test_search_strict_mode_only_principal_entries(tmp_path):
    store = _store_with_entries(tmp_path)
    results = store.search("hello", top_k=10, principal_id="alice", scope="strict")
    texts = [r.text for r in results]
    assert "alice entry" in texts
    assert "legacy entry" not in texts
    assert "bob entry" not in texts

