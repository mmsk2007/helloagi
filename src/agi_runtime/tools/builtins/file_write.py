"""Create or overwrite files."""

from pathlib import Path

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="file_write",
    description="Create a new file or overwrite an existing file with the given content.",
    toolset="system",
    risk="medium",
    parameters=[
        ToolParam("path", "string", "Absolute or relative path for the file"),
        ToolParam("content", "string", "The content to write to the file"),
        ToolParam("create_dirs", "boolean", "Create parent directories if they don't exist", required=False, default=True),
    ],
)
def file_write(path: str, content: str, create_dirs: bool = True) -> ToolResult:
    p = Path(path)

    try:
        if create_dirs:
            p.parent.mkdir(parents=True, exist_ok=True)

        p.write_text(content, encoding="utf-8")
        return ToolResult(ok=True, output=f"Written {len(content)} bytes to {path}")
    except Exception as e:
        return ToolResult(ok=False, output="", error=str(e))
