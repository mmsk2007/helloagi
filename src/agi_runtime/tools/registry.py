from dataclasses import dataclass
from typing import Callable, Dict


@dataclass
class ToolResult:
    ok: bool
    output: str


ToolFn = Callable[[str], ToolResult]


def _plan_tool(text: str) -> ToolResult:
    steps = [
        "Define objective and measurable success metrics",
        "Map constraints and risk boundaries",
        "Execute smallest high-leverage step",
        "Verify outcome and iterate",
    ]
    return ToolResult(True, "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)))


def _summarize_tool(text: str) -> ToolResult:
    words = text.split()
    short = " ".join(words[:30])
    return ToolResult(True, f"Summary: {short}{'...' if len(words) > 30 else ''}")


def _reflect_tool(text: str) -> ToolResult:
    return ToolResult(True, "Reflection: what worked, what failed, what to test next.")


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, ToolFn] = {
            "plan": _plan_tool,
            "summarize": _summarize_tool,
            "reflect": _reflect_tool,
        }

    def call(self, name: str, text: str) -> ToolResult:
        fn = self.tools.get(name)
        if not fn:
            return ToolResult(False, f"Unknown tool: {name}")
        return fn(text)
