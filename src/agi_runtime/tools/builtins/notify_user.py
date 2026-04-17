"""Send a non-blocking notification to the user."""

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="notify_user",
    description="Send a notification to the user without waiting for a response. Useful for status updates during long tasks.",
    toolset="user",
    risk="none",
    parameters=[
        ToolParam("message", "string", "The notification message"),
        ToolParam("level", "string", "Notification level: info, warning, success, error", required=False, default="info"),
    ],
)
def notify_user(message: str, level: str = "info") -> ToolResult:
    # The CLI/API layer intercepts this and displays it appropriately
    return ToolResult(ok=True, output=f"[NOTIFICATION:{level.upper()}] {message}")
