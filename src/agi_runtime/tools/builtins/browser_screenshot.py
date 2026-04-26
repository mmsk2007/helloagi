"""Capture a screenshot of the current browser session (requires Playwright)."""

from agi_runtime.tools.registry import ToolResult, RiskLevel, tool, get_tool_context_value


@tool(
    name="browser_screenshot",
    description="Save a PNG screenshot of the current page; returns filesystem path.",
    toolset="web",
    risk="low",
    parameters=[],
)
def browser_screenshot() -> ToolResult:
    if not get_tool_context_value("browser_enabled", True):
        return ToolResult(ok=False, output="", error="Browser tools disabled in configuration")
    from agi_runtime.browser.engine import get_browser_engine

    settings = get_tool_context_value("browser_settings") or {}
    eng = get_browser_engine(settings)
    sid = str(get_tool_context_value("principal_id") or "default")
    ok, path = eng.screenshot_path(sid)
    if not ok:
        return ToolResult(ok=False, output="", error=path)
    return ToolResult(ok=True, output=path)
