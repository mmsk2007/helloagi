"""Tests for text-only synthesis when the main tool loop hits max_turns."""

import asyncio

import pytest
from unittest.mock import MagicMock

from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.core.agent import HelloAGIAgent


@pytest.fixture
def agent():
    s = RuntimeSettings(
        memory_path="memory/test_identity_state.json",
        journal_path="memory/test_events.jsonl",
    )
    return HelloAGIAgent(settings=s)


def test_synthesize_claude_text_only_no_tools_in_request(agent: HelloAGIAgent):
    block = MagicMock()
    block.type = "text"
    block.text = "Here is a concise summary of the latest news."
    resp = MagicMock()
    resp.content = [block]
    agent._claude = MagicMock()
    agent._claude.messages.create = MagicMock(return_value=resp)
    agent._select_model = MagicMock(return_value="claude-3-5-haiku-20241022")
    agent._history = [
        {"role": "user", "content": "What are the latest news on AI?"},
    ]

    out = asyncio.run(
        agent._synthesize_claude_text_only("What are the latest news on AI?", "You are a helpful agent.")
    )

    assert "concise summary" in out
    agent._claude.messages.create.assert_called_once()
    kwargs = agent._claude.messages.create.call_args[1]
    assert "tools" not in kwargs


def test_message_after_max_turns_mentions_user_snippet(agent: HelloAGIAgent):
    msg = agent._message_after_max_turns("What are the latest news on AI?", 40, 40)
    assert "40" in msg
    assert "latest" in msg or "news" in msg


def test_synthesize_claude_text_only_returns_empty_on_error(agent: HelloAGIAgent):
    agent._claude = MagicMock()
    agent._claude.messages.create = MagicMock(side_effect=RuntimeError("API down"))
    agent._history = []
    out = asyncio.run(agent._synthesize_claude_text_only("hi", "sys"))
    assert out == ""


def test_tail_history_for_synthesis_long_thread(agent: HelloAGIAgent):
    agent._history = [{"role": "user", "content": f"m{i}"} for i in range(100)]
    tail = agent._tail_history_for_synthesis(10)
    assert len(tail) == 10
    assert tail[0]["content"] == "m90"
    assert tail[-1]["content"] == "m99"


def test_history_plaintext_for_gemini_includes_tool_results(agent: HelloAGIAgent):
    agent._history = [
        {"role": "user", "content": "news please"},
        {"role": "assistant", "content": "[tool_calls] web_search"},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "x1", "content": "Headline A"},
            ],
        },
    ]
    blob = agent._history_plaintext_for_gemini_synthesis(max_total=50_000)
    assert "news please" in blob
    assert "tool_result" in blob or "Headline A" in blob
