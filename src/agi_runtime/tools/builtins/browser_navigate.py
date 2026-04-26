"""Navigate to a URL in a governed browser session (Playwright or HTTP fallback)."""

from agi_runtime.tools.registry import ToolParam, ToolResult, RiskLevel, tool, get_tool_context_value


@tool(
    name="browser_navigate",
    description="Open a URL in the agent browser session and return visible page text.",
    toolset="web",
    risk="medium",
    parameters=[
        ToolParam("url", "string", "HTTPS or HTTP URL to open"),
    ],
)
def browser_navigate(url: str) -> ToolResult:
    if not get_tool_context_value("browser_enabled", True):
        return ToolResult(ok=False, output="", error="Browser tools disabled in configuration")
    from agi_runtime.browser.engine import get_browser_engine

    settings = get_tool_context_value("browser_settings") or {}
    eng = get_browser_engine(settings)
    sid = str(get_tool_context_value("principal_id") or "default")
    ok, text = eng.navigate(url, sid)
    if not ok:
        return ToolResult(ok=False, output="", error=text)
    return ToolResult(ok=True, output=text[:12000])
