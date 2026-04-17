"""Spawn an isolated sub-agent to handle a specific task."""

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="delegate_task",
    description="Spawn an isolated sub-agent to handle a specific task. The sub-agent gets a fresh context, restricted toolset, and its own SRG governance. You only see the summary result.",
    toolset="agents",
    risk="medium",
    parameters=[
        ToolParam("goal", "string", "The specific task/goal for the sub-agent"),
        ToolParam("context", "string", "Relevant context to pass to the sub-agent", required=False, default=""),
        ToolParam("toolset", "string", "Comma-separated list of tool names the sub-agent can use. Leave empty for default set.", required=False, default=""),
        ToolParam("max_turns", "integer", "Maximum turns for the sub-agent", required=False, default=15),
    ],
)
def delegate_task(goal: str, context: str = "", toolset: str = "", max_turns: int = 15) -> ToolResult:
    # This is a placeholder that gets intercepted by the agent loop.
    # The agent loop creates an actual sub-agent with isolated context.
    # See core/agent.py _handle_delegation()
    return ToolResult(
        ok=True,
        output=f"[DELEGATION_REQUEST] goal={goal} context_len={len(context)} toolset={toolset} max_turns={max_turns}"
    )
