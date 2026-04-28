"""Tests for ``HelloAGIAgent`` token streaming via ``messages.stream()``.

These tests pin three contracts:

1. ``agent.on_stream(text)`` is called for every text delta the SDK emits.
2. ``agent.on_stream(None)`` fires once per ``tool_use`` content-block start
   (so channels can finalize the in-flight streamed message before the next
   reasoning chunk).
3. ``stream.get_final_message()`` is what downstream code receives — the
   shape must remain identical to the old ``messages.create()`` return so
   the post-call code path (``response.content`` iteration, history append,
   tool-call accumulation) is unaffected.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterable, List
from unittest.mock import MagicMock

import pytest

from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.core.agent import HelloAGIAgent


@pytest.fixture
def agent():
    s = RuntimeSettings(
        memory_path="memory/test_identity_state.json",
        journal_path="memory/test_events.jsonl",
    )
    return HelloAGIAgent(settings=s)


def _delta_event(text: str):
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _tool_use_start_event(name: str = "web_fetch"):
    return SimpleNamespace(
        type="content_block_start",
        content_block=SimpleNamespace(
            type="tool_use", name=name, id="t1", input={}
        ),
    )


def _text_block_start_event():
    return SimpleNamespace(
        type="content_block_start",
        content_block=SimpleNamespace(type="text"),
    )


class _FakeStream:
    def __init__(self, events: Iterable[Any], final: Any):
        self._events = list(events)
        self._final = final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self):
        return self._final


def test_on_stream_emits_deltas(agent: HelloAGIAgent):
    received: List[Any] = []
    agent.on_stream = lambda chunk: received.append(chunk)

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Hello world"
    final = MagicMock()
    final.content = [text_block]

    events = [
        _text_block_start_event(),
        _delta_event("Hello "),
        _delta_event("world"),
    ]

    stream = _FakeStream(events, final)
    out = agent._drain_anthropic_stream(stream, agent.on_stream)

    assert received == ["Hello ", "world"]
    assert out is final


def test_on_stream_emits_none_at_tool_use_boundary(agent: HelloAGIAgent):
    received: List[Any] = []
    agent.on_stream = lambda chunk: received.append(chunk)

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "thinking..."
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "web_fetch"
    tool_block.id = "t1"
    tool_block.input = {}
    final = MagicMock()
    final.content = [text_block, tool_block]

    events = [
        _text_block_start_event(),
        _delta_event("thinking..."),
        _tool_use_start_event("web_fetch"),
    ]

    stream = _FakeStream(events, final)
    out = agent._drain_anthropic_stream(stream, agent.on_stream)

    # Pattern: text delta → segment break (None) at tool_use boundary.
    assert received == ["thinking...", None]
    assert out is final


def test_streaming_preserves_final_message_shape(agent: HelloAGIAgent):
    """Final message returned by drain matches what ``messages.create`` would have shaped."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Done."
    final = MagicMock()
    final.content = [text_block]

    stream = _FakeStream([_delta_event("Done.")], final)
    out = agent._drain_anthropic_stream(stream, None)  # no callback

    assert out is final
    assert out.content[0].type == "text"
    assert out.content[0].text == "Done."


def test_callback_exception_does_not_break_stream(agent: HelloAGIAgent):
    """A buggy ``on_stream`` callback must not stop the drain loop."""

    def bad(chunk):
        raise RuntimeError("kaboom")

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "ok"
    final = MagicMock()
    final.content = [text_block]

    stream = _FakeStream([_delta_event("a"), _delta_event("b")], final)
    out = agent._drain_anthropic_stream(stream, bad)

    # We should still reach the final message even though every callback raised.
    assert out is final


def test_synthesize_uses_messages_stream(agent: HelloAGIAgent):
    """The post-max-turns synthesis path now goes through ``messages.stream()``."""
    import asyncio

    block = MagicMock()
    block.type = "text"
    block.text = "synthesized answer"
    resp = MagicMock()
    resp.content = [block]

    agent._claude = MagicMock()
    agent._claude.messages.stream = MagicMock(
        return_value=_FakeStream([_delta_event("synthesized answer")], resp)
    )
    agent._select_model = MagicMock(return_value="claude-3-5-haiku-20241022")
    agent._history = [{"role": "user", "content": "hi"}]

    received: List[Any] = []
    agent.on_stream = lambda chunk: received.append(chunk)

    out = asyncio.run(agent._synthesize_claude_text_only("hi", "sys"))

    assert "synthesized answer" in out
    agent._claude.messages.stream.assert_called_once()
    assert received == ["synthesized answer"]
