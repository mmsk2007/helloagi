"""Recall information from persistent semantic memory."""

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="memory_recall",
    description="Search persistent memory for relevant information using semantic similarity.",
    toolset="memory",
    risk="low",
    parameters=[
        ToolParam("query", "string", "What to search for in memory"),
        ToolParam("top_k", "integer", "Maximum number of results to return", required=False, default=5),
    ],
)
def memory_recall(query: str, top_k: int = 5) -> ToolResult:
    from agi_runtime.memory.embeddings import GeminiEmbeddingStore

    store = GeminiEmbeddingStore()

    if store.available and store.count() > 0:
        results = store.search(query, top_k=top_k)
        if results:
            output_parts = []
            for r in results:
                cat = r.metadata.get("category", "unknown")
                output_parts.append(f"[{cat}] (score: {r.score:.3f}) {r.text}")
            return ToolResult(ok=True, output="\n\n".join(output_parts))
        return ToolResult(ok=True, output="No relevant memories found.")
    else:
        # Fallback: search text file
        from pathlib import Path
        mem_file = Path("memory/facts.txt")
        if mem_file.exists():
            lines = mem_file.read_text(encoding="utf-8").splitlines()
            query_lower = query.lower()
            matches = [ln for ln in lines if query_lower in ln.lower()]
            if matches:
                return ToolResult(ok=True, output="\n".join(matches[:top_k]))
        return ToolResult(ok=True, output="No memories stored yet.")
