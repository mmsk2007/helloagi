"""OpenAI Chat Completions adapter: Claude-style tool schemas and history."""

from __future__ import annotations

import json
from typing import Any, Callable, List, Optional, Tuple


def claude_tool_schemas_to_openai(claude_tools: List[dict]) -> List[dict]:
    """Map HelloAGI / Anthropic tool dicts to OpenAI ``tools`` API shape."""
    out: List[dict] = []
    for t in claude_tools or []:
        name = (t.get("name") or "").strip()
        if not name:
            continue
        desc = (t.get("description") or "")[:4096]
        inp = t.get("input_schema")
        if not isinstance(inp, dict):
            inp = {"type": "object", "properties": {}}
        if inp.get("type") != "object":
            inp = {"type": "object", "properties": {}}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": inp,
                },
            }
        )
    return out


def _block_type(block: Any) -> Optional[str]:
    if isinstance(block, dict):
        return str(block.get("type") or "")
    return str(getattr(block, "type", "") or "")


def _text_from_block(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("text") or "")
    return str(getattr(block, "text", "") or "")


def _tool_use_from_block(block: Any) -> Tuple[Optional[str], str, dict]:
    if isinstance(block, dict):
        tid = block.get("id")
        name = block.get("name") or ""
        raw_in = block.get("input")
    else:
        tid = getattr(block, "id", None)
        name = getattr(block, "name", "") or ""
        raw_in = getattr(block, "input", None)
    if isinstance(raw_in, dict):
        inp = raw_in
    else:
        try:
            inp = json.loads(raw_in) if isinstance(raw_in, str) and raw_in.strip() else {}
        except Exception:
            inp = {}
    return (str(tid) if tid else None), str(name or ""), inp


def claude_history_to_openai_messages(
    history: List[dict],
    *,
    system_prompt: str,
) -> List[dict]:
    """Convert internal Claude-style ``_history`` entries to OpenAI chat messages."""
    messages: List[dict] = [{"role": "system", "content": system_prompt}]
    for m in history or []:
        role = (m.get("role") or "").strip().lower()
        content = m.get("content")

        if role == "user":
            if isinstance(content, str):
                messages.append({"role": "user", "content": content})
                continue
            if isinstance(content, list):
                tool_msgs: List[dict] = []
                other: List[str] = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "tool_result":
                        tid = str(item.get("tool_use_id") or "")
                        body = item.get("content", "")
                        if not isinstance(body, str):
                            body = str(body)
                        tool_msgs.append({"role": "tool", "tool_call_id": tid, "content": body[:32000]})
                    else:
                        other.append(json.dumps(item)[:2000])
                for tm in tool_msgs:
                    messages.append(tm)
                if other:
                    messages.append({"role": "user", "content": "\n".join(other)})
                continue
            messages.append({"role": "user", "content": str(content)})

        elif role == "assistant":
            if not isinstance(content, list):
                messages.append({"role": "assistant", "content": str(content or "")})
                continue
            text_parts: List[str] = []
            tool_calls: List[dict] = []
            for block in content:
                btype = _block_type(block)
                if btype == "text":
                    text_parts.append(_text_from_block(block))
                elif btype == "tool_use":
                    tid, name, inp = _tool_use_from_block(block)
                    if not tid or not name:
                        continue
                    try:
                        args = json.dumps(inp, ensure_ascii=False)
                    except Exception:
                        args = "{}"
                    tool_calls.append(
                        {
                            "id": tid,
                            "type": "function",
                            "function": {"name": name, "arguments": args[:24000]},
                        }
                    )
                # thinking / redacted_thinking: skip for OpenAI
            text_joined = "\n".join(text_parts).strip()
            payload: dict = {"role": "assistant"}
            payload["content"] = text_joined if text_joined else ""
            if tool_calls:
                payload["tool_calls"] = tool_calls
            messages.append(payload)
        else:
            messages.append({"role": "user", "content": f"[{role}]\n{content!s}"[:8000]})
    return messages


async def openai_chat_completion(
    client: Any,
    *,
    model: str,
    messages: List[dict],
    tools: Optional[List[dict]],
    max_tokens: int = 8192,
    on_stream: Optional[Callable[[str], None]] = None,
) -> Any:
    """Single non-streaming chat completion; ``on_stream`` reserved for future."""
    _ = on_stream
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": min(max_tokens, 16384),
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return await client.chat.completions.create(**kwargs)


def parse_openai_assistant_message(message: Any) -> Tuple[str, List[dict]]:
    """Return (text, tool_calls) from a ChatCompletionMessage-like object."""
    text = (getattr(message, "content", None) or "") or ""
    raw_calls = list(getattr(message, "tool_calls", None) or [])
    tool_calls: List[dict] = []
    for tc in raw_calls:
        fn = getattr(tc, "function", None)
        if fn is None and isinstance(tc, dict):
            fn = tc.get("function") or {}
        if fn is None:
            continue
        if isinstance(fn, dict):
            name = str(fn.get("name") or "")
            args = fn.get("arguments", "") or "{}"
        else:
            name = getattr(fn, "name", "") or ""
            args = getattr(fn, "arguments", "") or "{}"
        tid = getattr(tc, "id", None)
        if tid is None and isinstance(tc, dict):
            tid = tc.get("id")
        tid = str(tid or "")
        if not name or not tid:
            continue
        try:
            inp = json.loads(args) if isinstance(args, str) else dict(args)
        except Exception:
            inp = {}
        tool_calls.append({"id": tid, "name": name, "input": inp})
    return str(text).strip(), tool_calls


def assistant_content_as_anthropic_shapes(text: str, tool_calls: List[dict]) -> List[Any]:
    """Anthropic-shaped assistant blocks (``SimpleNamespace``) for ``_history``."""
    from types import SimpleNamespace

    blocks: List[Any] = []
    if text:
        blocks.append(SimpleNamespace(type="text", text=text))
    for tc in tool_calls:
        blocks.append(
            SimpleNamespace(
                type="tool_use",
                id=tc["id"],
                name=tc["name"],
                input=tc.get("input") or {},
            )
        )
    return blocks
