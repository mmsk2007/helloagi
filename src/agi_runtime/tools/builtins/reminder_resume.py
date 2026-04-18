"""Resume a paused reminder."""

from agi_runtime.reminders.service import ReminderService
from agi_runtime.tools.registry import (
    ToolParam,
    ToolResult,
    get_tool_context_value,
    tool,
)


@tool(
    name="reminder_resume",
    description="Resume a paused reminder by id.",
    toolset="user",
    risk="none",
    parameters=[ToolParam("job_id", "string", "Reminder id to resume")],
)
def reminder_resume(job_id: str) -> ToolResult:
    principal_id = str(get_tool_context_value("principal_id") or "")
    svc = ReminderService()
    return ToolResult(ok=True, output=svc.resume(principal_id=principal_id, job_id=job_id))

