"""Search for files by name pattern and content."""

import fnmatch
import os
from pathlib import Path

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="file_search",
    description="Search for files by name pattern (glob) and optionally filter by content. Returns matching file paths with preview.",
    toolset="system",
    risk="low",
    parameters=[
        ToolParam("directory", "string", "Directory to search in"),
        ToolParam("pattern", "string", "Glob pattern for file names (e.g. '*.py', '**/*.js')", required=False, default="*"),
        ToolParam("content_query", "string", "Only return files containing this text", required=False),
        ToolParam("max_results", "integer", "Maximum number of results to return", required=False, default=20),
    ],
)
def file_search(directory: str, pattern: str = "*", content_query: str = None, max_results: int = 20) -> ToolResult:
    root = Path(directory)
    if not root.exists():
        return ToolResult(ok=False, output="", error=f"Directory not found: {directory}")

    matches = []
    try:
        for p in root.rglob(pattern):
            if not p.is_file():
                continue
            if content_query:
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                    if content_query not in text:
                        continue
                    # Find matching line for preview
                    for i, line in enumerate(text.splitlines(), 1):
                        if content_query in line:
                            matches.append(f"{p}:{i}: {line.strip()[:120]}")
                            break
                except Exception:
                    continue
            else:
                matches.append(str(p))

            if len(matches) >= max_results:
                break
    except Exception as e:
        return ToolResult(ok=False, output="", error=str(e))

    if not matches:
        return ToolResult(ok=True, output="No files found matching criteria.")

    output = "\n".join(matches)
    if len(matches) >= max_results:
        output += f"\n... (showing first {max_results} results)"

    return ToolResult(ok=True, output=output)
