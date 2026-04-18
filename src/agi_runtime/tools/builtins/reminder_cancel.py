"""Cancel and remove a reminder."""

from agi_runtime.reminders.service import ReminderService
from agi_runtime.tools.registry import (
    ToolParam,
    ToolResult,
    get_tool_context_value,
    tool,
)


@tool(
    name="reminder_cancel",
    description="Cancel and remove a reminder by id.",
    toolset="user",
    risk="none",
    parameters=[ToolParam("job_id", "string", "Reminder id to cancel")],
)
def reminder_cancel(job_id: str) -> ToolResult:
    principal_id = str(get_tool_context_value("principal_id") or "")
    svc = ReminderService()
    return ToolResult(ok=True, output=svc.cancel(principal_id=principal_id, job_id=job_id))

