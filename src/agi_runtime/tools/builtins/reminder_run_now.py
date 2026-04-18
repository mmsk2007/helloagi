"""Force a reminder to run immediately."""

from agi_runtime.reminders.service import ReminderService
from agi_runtime.tools.registry import (
    ToolParam,
    ToolResult,
    get_tool_context_value,
    tool,
)


@tool(
    name="reminder_run_now",
    description="Run a reminder immediately by id.",
    toolset="user",
    risk="low",
    parameters=[ToolParam("job_id", "string", "Reminder id to run now")],
)
def reminder_run_now(job_id: str) -> ToolResult:
    principal_id = str(get_tool_context_value("principal_id") or "")
    svc = ReminderService()
    return ToolResult(ok=True, output=svc.run_now(principal_id=principal_id, job_id=job_id))

