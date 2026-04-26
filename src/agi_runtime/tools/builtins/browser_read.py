"""Read text from the current browser session page."""

from agi_runtime.tools.registry import ToolParam, ToolResult, RiskLevel, tool, get_tool_context_value


@tool(
    name="browser_read",
    description="Return text from the last page loaded with browser_navigate.",
    toolset="web",
    risk="low",
    parameters=[],
)
def browser_read() -> ToolResult:
    if not get_tool_context_value("browser_enabled", True):
        return ToolResult(ok=False, output="", error="Browser tools disabled in configuration")
    from agi_runtime.browser.engine import get_browser_engine

    settings = get_tool_context_value("browser_settings") or {}
    eng = get_browser_engine(settings)
    sid = str(get_tool_context_value("principal_id") or "default")
    text = eng.read_page(sid)
    if not text:
        return ToolResult(ok=False, output="", error="No page loaded; run browser_navigate first")
    return ToolResult(ok=True, output=text[:12000])
