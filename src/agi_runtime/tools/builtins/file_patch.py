"""Surgical find-and-replace in files."""

from pathlib import Path

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="file_patch",
    description="Replace a specific text block in a file. The old_text must match exactly.",
    toolset="system",
    risk="medium",
    parameters=[
        ToolParam("path", "string", "Path to the file to patch"),
        ToolParam("old_text", "string", "The exact text to find and replace"),
        ToolParam("new_text", "string", "The replacement text"),
    ],
)
def file_patch(path: str, old_text: str, new_text: str) -> ToolResult:
    p = Path(path)
    if not p.exists():
        return ToolResult(ok=False, output="", error=f"File not found: {path}")

    try:
        content = p.read_text(encoding="utf-8")
    except Exception as e:
        return ToolResult(ok=False, output="", error=f"Cannot read file: {e}")

    if old_text not in content:
        return ToolResult(ok=False, output="", error="old_text not found in file. Make sure it matches exactly (including whitespace).")

    count = content.count(old_text)
    new_content = content.replace(old_text, new_text, 1)
    p.write_text(new_content, encoding="utf-8")

    return ToolResult(ok=True, output=f"Patched {path} (replaced 1 of {count} occurrence(s))")
