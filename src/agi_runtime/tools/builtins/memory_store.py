"""Store facts and insights to persistent semantic memory."""

from agi_runtime.tools.registry import (
    tool,
    ToolParam,
    ToolResult,
    get_tool_context_value,
)


@tool(
    name="memory_store",
    description="Store a fact, insight, or piece of information to persistent memory. Stored memories can be recalled later via semantic search.",
    toolset="memory",
    risk="low",
    parameters=[
        ToolParam("content", "string", "The fact or insight to remember"),
        ToolParam("category", "string", "Category: fact, preference, skill, environment, insight", required=False, default="fact"),
    ],
)
def memory_store(content: str, category: str = "fact") -> ToolResult:
    from agi_runtime.memory.embeddings import GeminiEmbeddingStore

    store = GeminiEmbeddingStore()

    principal_id = get_tool_context_value("memory_principal_id") or get_tool_context_value("principal_id")
    if store.available:
        success = store.add(
            content,
            metadata={"category": category},
            principal_id=principal_id,
        )
        if success:
            return ToolResult(ok=True, output=f"Stored to semantic memory [{category}]: {content[:100]}...")
        return ToolResult(ok=False, output="", error="Failed to generate embedding. Check GOOGLE_API_KEY.")
    else:
        # Fallback: store to simple text file
        from pathlib import Path
        mem_file = Path("memory/facts.txt")
        mem_file.parent.mkdir(parents=True, exist_ok=True)
        prefix = f"[principal:{principal_id}] " if principal_id else ""
        with mem_file.open("a", encoding="utf-8") as f:
            f.write(f"{prefix}[{category}] {content}\n")
        return ToolResult(ok=True, output=f"Stored to file memory [{category}]: {content[:100]}...")
