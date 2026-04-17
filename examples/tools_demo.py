"""Tools Demo — Shows HelloAGI's built-in tool ecosystem.

HelloAGI has 17+ tools organized by toolset:
system, web, code, memory, agents, user
"""
import os
import sys
import asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agi_runtime.tools.registry import ToolRegistry, discover_builtin_tools

# Initialize and discover tools
registry = ToolRegistry.get_instance()
discover_builtin_tools()

# List all tools
tools = registry.list_tools()
print(f"=== HelloAGI Tools ({len(tools)} available) ===\n")

current_toolset = None
for t in sorted(tools, key=lambda x: (x.toolset.value, x.name)):
    if t.toolset != current_toolset:
        current_toolset = t.toolset
        print(f"\n[{current_toolset.value.upper()}]")
    risk_icon = {"none": "⬜", "low": "🟢", "medium": "🟡", "high": "🔴"}[t.risk.value]
    print(f"  {risk_icon} {t.name}: {t.description}")

# Execute a tool
print("\n\n=== Tool Execution Demo ===\n")

async def demo():
    # Read a file
    result = await registry.execute("file_read", {"path": "README.md", "max_lines": 5})
    print(f"file_read: ok={result.ok}")
    print(f"  Output: {result.to_content()[:200]}")
    print()

    # Search files
    result = await registry.execute("file_search", {"pattern": "*.py", "directory": "src/agi_runtime/core"})
    print(f"file_search: ok={result.ok}")
    print(f"  Output: {result.to_content()[:200]}")

asyncio.run(demo())
