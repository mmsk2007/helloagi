"""List reminders for the current principal."""

from agi_runtime.reminders.service import ReminderService
from agi_runtime.tools.registry import (
    ToolResult,
    get_tool_context_value,
    tool,
)


@tool(
    name="reminder_list",
    description="List reminders for the current user/chat principal.",
    toolset="user",
    risk="none",
    parameters=[],
)
def reminder_list() -> ToolResult:
    principal_id = str(get_tool_context_value("principal_id") or "")
    svc = ReminderService()
    return ToolResult(ok=True, output=svc.list_for_principal(principal_id))

