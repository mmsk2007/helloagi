"""Search past conversation sessions in the journal."""

import json
from pathlib import Path

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="session_search",
    description="Search across past conversation history in the event journal. Returns matching events with context.",
    toolset="memory",
    risk="low",
    parameters=[
        ToolParam("query", "string", "Text to search for in past conversations"),
        ToolParam("max_results", "integer", "Maximum number of results", required=False, default=10),
        ToolParam("event_type", "string", "Filter by event type (input, response, tool, deny, etc.)", required=False),
    ],
)
def session_search(query: str, max_results: int = 10, event_type: str = None) -> ToolResult:
    # Default journal path
    journal_path = Path("memory/events.jsonl")
    if not journal_path.exists():
        return ToolResult(ok=True, output="No conversation history found.")

    query_lower = query.lower()
    matches = []

    try:
        with journal_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Filter by event type
                if event_type and event.get("kind") != event_type:
                    continue

                # Search in payload
                payload_str = json.dumps(event.get("payload", {}), ensure_ascii=False).lower()
                if query_lower in payload_str:
                    import time as _time
                    ts = event.get("ts", 0)
                    try:
                        time_str = _time.strftime("%Y-%m-%d %H:%M", _time.localtime(ts))
                    except Exception:
                        time_str = str(ts)

                    kind = event.get("kind", "unknown")
                    payload = event.get("payload", {})
                    preview = json.dumps(payload, ensure_ascii=False)[:200]
                    matches.append(f"[{time_str}] ({kind}) {preview}")

                    if len(matches) >= max_results:
                        break
    except Exception as e:
        return ToolResult(ok=False, output="", error=f"Journal search failed: {e}")

    if not matches:
        return ToolResult(ok=True, output=f"No events matching '{query}' found in history.")

    return ToolResult(ok=True, output="\n\n".join(matches))
