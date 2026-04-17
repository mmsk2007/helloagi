"""Request human input or confirmation."""

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="ask_user",
    description="Ask the user a question or request clarification. Use this when you need more information to proceed.",
    toolset="user",
    risk="none",
    parameters=[
        ToolParam("question", "string", "The question to ask the user"),
    ],
)
def ask_user(question: str) -> ToolResult:
    # In CLI mode, this prompts the user directly.
    # In API/channel mode, the question is returned as a special response.
    # The agent loop handles this by checking for ask_user tool calls.
    return ToolResult(ok=True, output=f"[AWAITING_USER_INPUT] {question}")
