"""Send a local file as an attachment via the active channel."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from agi_runtime.tools.registry import (
    tool,
    ToolParam,
    ToolResult,
    get_tool_context_value,
)

logger = logging.getLogger("helloagi.tools.send_file")


@tool(
    name="send_file",
    description=(
        "Send a local file to the user as an attachment through the active channel "
        "(e.g. Telegram document). Pass an absolute path to a file you have already "
        "created with file_write or that exists on disk. If the channel cannot deliver "
        "attachments, the path is returned to the user as text."
    ),
    toolset="user",
    risk="medium",
    parameters=[
        ToolParam("path", "string", "Absolute path to the file to send"),
        ToolParam("caption", "string", "Optional short caption shown with the file", required=False, default=""),
        ToolParam("filename", "string", "Optional display filename; defaults to the path basename", required=False, default=""),
    ],
)
def send_file(path: str, caption: str = "", filename: str = "") -> ToolResult:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return ToolResult(ok=False, output="", error=f"file not found: {path}")
    size = p.stat().st_size

    channel = get_tool_context_value("channel")
    channel_id = get_tool_context_value("channel_id")

    if channel is None or "file" not in getattr(channel, "capabilities", frozenset()):
        return ToolResult(
            ok=True,
            output=f"[file ready] {p} ({size} bytes) — current channel does not deliver attachments; share the path with the user.",
        )

    if not channel_id:
        return ToolResult(ok=False, output="", error="no active channel_id; cannot route the file")

    loop = getattr(channel, "_loop", None)
    if loop is None or not loop.is_running():
        return ToolResult(ok=False, output="", error="channel event loop is not running")

    t0 = time.monotonic()
    try:
        result = asyncio.run_coroutine_threadsafe(
            channel.send_file(channel_id, str(p), caption=caption, filename=filename),
            loop,
        ).result(timeout=60.0)
    except Exception as exc:
        return ToolResult(ok=False, output="", error=f"send_file dispatch failed: {exc}")

    dur_ms = (time.monotonic() - t0) * 1000.0
    logger.info(
        "file out tool=send_file channel=%s path=%s size=%d ms=%.1f ok=%s",
        type(channel).__name__, p, size, dur_ms, result.get("ok"),
    )
    if result.get("ok"):
        return ToolResult(ok=True, output=f"delivered {p.name} ({size} bytes) to {channel.name}")
    return ToolResult(ok=False, output="", error=str(result.get("error") or "unknown send error"))
