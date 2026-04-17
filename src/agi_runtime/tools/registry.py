"""World-class tool registry with decorator-based registration.

Every tool self-registers at import time. Tools declare:
- name, description, parameters (JSON Schema auto-generated)
- toolset grouping (system, web, code, memory, agents, media, user)
- risk level (none, low, medium, high) → used by SRG governance
- availability check (optional, gates on API keys / OS / deps)
"""

from __future__ import annotations

import asyncio
import inspect
import json
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, get_type_hints


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Toolset(str, Enum):
    SYSTEM = "system"
    WEB = "web"
    CODE = "code"
    MEMORY = "memory"
    AGENTS = "agents"
    MEDIA = "media"
    USER = "user"


@dataclass
class ToolParam:
    name: str
    type: str  # "string", "integer", "boolean", "number", "array", "object"
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None


@dataclass
class ToolDef:
    """A registered tool definition."""
    name: str
    description: str
    toolset: Toolset
    risk: RiskLevel
    parameters: List[ToolParam] = field(default_factory=list)
    handler: Optional[Callable] = None
    check_fn: Optional[Callable[[], bool]] = None
    is_async: bool = False

    def to_claude_schema(self) -> dict:
        """Generate Claude API tool_use schema for this tool."""
        properties = {}
        required = []
        for p in self.parameters:
            prop: Dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        schema: Dict[str, Any] = {
            "name": self.name,
            "description": f"{self.description} [risk: {self.risk.value}]",
            "input_schema": {
                "type": "object",
                "properties": properties,
            },
        }
        if required:
            schema["input_schema"]["required"] = required
        return schema

    @property
    def available(self) -> bool:
        if self.check_fn is None:
            return True
        try:
            return self.check_fn()
        except Exception:
            return False


@dataclass
class ToolResult:
    """Result of a tool execution."""
    ok: bool
    output: str
    error: Optional[str] = None

    def to_content(self) -> str:
        if self.ok:
            return self.output
        return f"Error: {self.error or self.output}"


class ToolRegistry:
    """Central tool registry. Tools register themselves at import time."""

    _instance: Optional['ToolRegistry'] = None

    def __init__(self):
        self._tools: Dict[str, ToolDef] = {}

    @classmethod
    def get_instance(cls) -> 'ToolRegistry':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, tool_def: ToolDef):
        """Register a tool definition."""
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> Optional[ToolDef]:
        return self._tools.get(name)

    def list_tools(self, toolset: Optional[Toolset] = None) -> List[ToolDef]:
        tools = list(self._tools.values())
        if toolset:
            tools = [t for t in tools if t.toolset == toolset]
        return [t for t in tools if t.available]

    def get_schemas(self, toolset: Optional[Toolset] = None) -> List[dict]:
        """Get Claude-format tool schemas for all available tools."""
        return [t.to_claude_schema() for t in self.list_tools(toolset)]

    async def execute(self, name: str, params: dict) -> ToolResult:
        """Execute a tool by name with given parameters."""
        tool_def = self._tools.get(name)
        if not tool_def:
            return ToolResult(ok=False, output="", error=f"Unknown tool: {name}")

        if not tool_def.available:
            return ToolResult(ok=False, output="", error=f"Tool '{name}' is not available (missing dependencies or API keys)")

        if not tool_def.handler:
            return ToolResult(ok=False, output="", error=f"Tool '{name}' has no handler")

        try:
            if tool_def.is_async:
                result = await tool_def.handler(**params)
            else:
                result = tool_def.handler(**params)

            if isinstance(result, ToolResult):
                return result
            return ToolResult(ok=True, output=str(result))

        except Exception as e:
            tb = traceback.format_exc()
            return ToolResult(ok=False, output="", error=f"{type(e).__name__}: {e}\n{tb[-500:]}")

    def call_sync(self, name: str, params: dict) -> ToolResult:
        """Synchronous wrapper for execute()."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.execute(name, params))
                return future.result()
        return asyncio.run(self.execute(name, params))


# --- Decorator API ---

def tool(
    name: str,
    description: str,
    toolset: Toolset | str,
    risk: RiskLevel | str = RiskLevel.LOW,
    parameters: Optional[List[ToolParam]] = None,
    check_fn: Optional[Callable[[], bool]] = None,
):
    """Decorator to register a function as a tool.

    Usage:
        @tool(
            name="bash_exec",
            description="Execute a shell command",
            toolset="system",
            risk="high",
            parameters=[
                ToolParam("command", "string", "The shell command to execute"),
            ],
        )
        def bash_exec(command: str) -> ToolResult:
            ...
    """
    if isinstance(toolset, str):
        toolset = Toolset(toolset)
    if isinstance(risk, str):
        risk = RiskLevel(risk)

    def decorator(fn: Callable) -> Callable:
        is_async = inspect.iscoroutinefunction(fn)
        tool_def = ToolDef(
            name=name,
            description=description,
            toolset=toolset,
            risk=risk,
            parameters=parameters or [],
            handler=fn,
            check_fn=check_fn,
            is_async=is_async,
        )
        ToolRegistry.get_instance().register(tool_def)
        fn._tool_def = tool_def
        return fn

    return decorator


def discover_builtin_tools():
    """Import all builtin tool modules to trigger registration."""
    import importlib
    import pkgutil
    from agi_runtime.tools import builtins as builtins_pkg

    for importer, modname, ispkg in pkgutil.iter_modules(builtins_pkg.__path__):
        importlib.import_module(f"agi_runtime.tools.builtins.{modname}")
