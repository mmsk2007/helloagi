"""Send an image (local file or URL) via the active channel."""

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

logger = logging.getLogger("helloagi.tools.send_image")


@tool(
    name="send_image",
    description=(
        "Send an image to the user through the active channel. Accepts either an "
        "absolute path to a local image file or an http(s) URL. If the channel "
        "cannot deliver images, the source is returned to the user as text."
    ),
    toolset="user",
    risk="medium",
    parameters=[
        ToolParam("path_or_url", "string", "Absolute file path OR http(s) URL of the image"),
        ToolParam("caption", "string", "Optional short caption shown with the image", required=False, default=""),
    ],
)
def send_image(path_or_url: str, caption: str = "") -> ToolResult:
    is_url = path_or_url.lower().startswith(("http://", "https://"))
    size = 0
    if not is_url:
        p = Path(path_or_url)
        if not p.exists() or not p.is_file():
            return ToolResult(ok=False, output="", error=f"file not found: {path_or_url}")
        size = p.stat().st_size

    channel = get_tool_context_value("channel")
    channel_id = get_tool_context_value("channel_id")

    if channel is None or "image" not in getattr(channel, "capabilities", frozenset()):
        return ToolResult(
            ok=True,
            output=f"[image ready] {path_or_url} — current channel does not deliver images; share the source with the user.",
        )

    if not channel_id:
        return ToolResult(ok=False, output="", error="no active channel_id; cannot route the image")

    loop = getattr(channel, "_loop", None)
    if loop is None or not loop.is_running():
        return ToolResult(ok=False, output="", error="channel event loop is not running")

    t0 = time.monotonic()
    try:
        result = asyncio.run_coroutine_threadsafe(
            channel.send_image(channel_id, path_or_url, caption=caption),
            loop,
        ).result(timeout=60.0)
    except Exception as exc:
        return ToolResult(ok=False, output="", error=f"send_image dispatch failed: {exc}")

    dur_ms = (time.monotonic() - t0) * 1000.0
    logger.info(
        "img out  tool=send_image channel=%s src=%s size=%d ms=%.1f ok=%s",
        type(channel).__name__, path_or_url, size, dur_ms, result.get("ok"),
    )
    if result.get("ok"):
        return ToolResult(ok=True, output=f"delivered image to {channel.name}")
    return ToolResult(ok=False, output="", error=str(result.get("error") or "unknown send error"))
