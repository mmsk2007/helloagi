"""Read files with optional line ranges and keyword search."""

from pathlib import Path

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="file_read",
    description="Read a file's contents. Supports line ranges and keyword filtering.",
    toolset="system",
    risk="low",
    parameters=[
        ToolParam("path", "string", "Absolute or relative path to the file"),
        ToolParam("start_line", "integer", "Start reading from this line (1-based)", required=False),
        ToolParam("end_line", "integer", "Stop reading at this line (inclusive)", required=False),
        ToolParam("keyword", "string", "Only return lines containing this keyword", required=False),
    ],
)
def file_read(path: str, start_line: int = None, end_line: int = None, keyword: str = None) -> ToolResult:
    p = Path(path)
    if not p.exists():
        return ToolResult(ok=False, output="", error=f"File not found: {path}")
    if not p.is_file():
        return ToolResult(ok=False, output="", error=f"Not a file: {path}")

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return ToolResult(ok=False, output="", error=f"Cannot read file: {e}")

    lines = text.splitlines(keepends=True)

    # Apply line range
    if start_line is not None or end_line is not None:
        s = (start_line or 1) - 1
        e = end_line or len(lines)
        lines = lines[s:e]

    # Apply keyword filter
    if keyword:
        lines = [ln for ln in lines if keyword in ln]

    if not lines:
        return ToolResult(ok=True, output="(no matching content)")

    # Truncate very large outputs
    output = "".join(lines)
    if len(output) > 100000:
        output = output[:100000] + "\n... (truncated)"

    return ToolResult(ok=True, output=output)
