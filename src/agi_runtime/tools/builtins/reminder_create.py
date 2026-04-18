"""Create a scheduled reminder for the current principal."""

from agi_runtime.reminders.service import ReminderService
from agi_runtime.tools.registry import (
    ToolParam,
    ToolResult,
    get_tool_context_value,
    tool,
)


@tool(
    name="reminder_create",
    description="Create a reminder using natural time text or cron expression.",
    toolset="user",
    risk="low",
    parameters=[
        ToolParam("message", "string", "Reminder text to send"),
        ToolParam("schedule", "string", "Schedule: 'in 30m', 'tomorrow 9am', or 'cron:0 9 * * *'"),
        ToolParam("timezone", "string", "IANA timezone (e.g. UTC, Asia/Riyadh)", required=False, default="UTC"),
    ],
)
def reminder_create(message: str, schedule: str, timezone: str = "UTC") -> ToolResult:
    principal_id = str(get_tool_context_value("principal_id") or "")
    svc = ReminderService()
    result = svc.create(principal_id=principal_id, message=message, schedule=schedule, timezone=timezone)
    if not result.ok:
        return ToolResult(ok=False, output="", error=result.message)
    return ToolResult(ok=True, output=result.message)

