"""Tests for Telegram live tool preview (HELLOAGI_TELEGRAM_LIVE)."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agi_runtime.channels.telegram import (
    TelegramChannel,
    _env_telegram_live_debounce_s,
    _env_telegram_live_enabled,
)
from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.core.agent import HelloAGIAgent


@pytest.fixture
def agent():
    return HelloAGIAgent(
        settings=RuntimeSettings(
            memory_path="memory/test_identity_state.json",
            journal_path="memory/test_events.jsonl",
        )
    )


def test_env_telegram_live_flag():
    old = os.environ.get("HELLOAGI_TELEGRAM_LIVE")
    try:
        os.environ.pop("HELLOAGI_TELEGRAM_LIVE", None)
        assert _env_telegram_live_enabled() is True
        os.environ["HELLOAGI_TELEGRAM_LIVE"] = "1"
        assert _env_telegram_live_enabled() is True
        os.environ["HELLOAGI_TELEGRAM_LIVE"] = "0"
        assert _env_telegram_live_enabled() is False
    finally:
        if old is None:
            os.environ.pop("HELLOAGI_TELEGRAM_LIVE", None)
        else:
            os.environ["HELLOAGI_TELEGRAM_LIVE"] = old


def test_env_telegram_live_debounce_bounds():
    old = os.environ.get("HELLOAGI_TELEGRAM_LIVE_MIN_INTERVAL_MS")
    try:
        os.environ["HELLOAGI_TELEGRAM_LIVE_MIN_INTERVAL_MS"] = "99999"
        assert _env_telegram_live_debounce_s() == 5.0
        os.environ["HELLOAGI_TELEGRAM_LIVE_MIN_INTERVAL_MS"] = "3"
        assert _env_telegram_live_debounce_s() == 0.2
    finally:
        if old is None:
            os.environ.pop("HELLOAGI_TELEGRAM_LIVE_MIN_INTERVAL_MS", None)
        else:
            os.environ["HELLOAGI_TELEGRAM_LIVE_MIN_INTERVAL_MS"] = old


def test_format_tool_progress_lines():
    assert "web_search" in TelegramChannel._format_tool_progress_start("web_search", "allow")
    assert "blocked" in TelegramChannel._format_tool_progress_start("x", "deny").lower()
    assert "✓" in TelegramChannel._format_tool_progress_end("bash_exec", True)


def test_live_coalesce_debounced_edit(agent: HelloAGIAgent):
    channel = TelegramChannel(agent=agent, token="dummy")
    edits = []

    async def edit_message_text(*, chat_id, message_id, text, **kwargs):
        edits.append({"chat_id": chat_id, "message_id": message_id, "text": text})

    bot = MagicMock()
    bot.edit_message_text = AsyncMock(side_effect=edit_message_text)

    st = {
        "chat_id": 42,
        "message_id": 7,
        "bot": bot,
        "debounce_s": 0.05,
        "lines": [],
        "debounce_task": None,
    }

    async def run():
        await channel._live_coalesce_edit(st, "🛠 a…")
        await channel._live_coalesce_edit(st, "✓ a")
        await asyncio.sleep(0.12)

    asyncio.run(run())
    assert len(edits) >= 1
    assert "✓ a" in edits[-1]["text"]


def test_handlers_restored_after_message_handler_finally(agent: HelloAGIAgent):
    """on_tool_start/end set during a run are restored to previous values after the block."""
    channel = TelegramChannel(agent=agent, token="dummy")
    orig_s = agent.on_tool_start
    orig_e = agent.on_tool_end
    agent.principals.update("telegram:dm:1", onboarded=True, preferred_name="u")

    def fake_think(_p, _t):
        assert agent.on_tool_start is not orig_s
        assert agent.on_tool_end is not orig_e
        from agi_runtime.core.agent import AgentResponse

        return AgentResponse(text="ok", decision="allow", risk=0.1, tool_calls_made=0, turns_used=1)

    async def run():
        upd = MagicMock()
        upd.effective_user = MagicMock(id=1)
        upd.effective_chat = MagicMock(id=2, type="private")
        upd.message = MagicMock()
        upd.message.text = "hello"
        upd.message.message_id = 100
        upd.message.reply_text = AsyncMock()

        ctx = MagicMock()
        ctx.bot = MagicMock()
        ctx.bot.send_chat_action = AsyncMock()
        ctx.bot.send_message = AsyncMock(
            return_value=MagicMock(message_id=55)
        )
        ctx.bot.edit_message_text = AsyncMock()
        ctx.bot.delete_message = AsyncMock()

        channel._loop = asyncio.get_running_loop()
        channel._app = MagicMock()
        channel._app.bot = ctx.bot

        with (
            patch.dict(os.environ, {"HELLOAGI_TELEGRAM_LIVE": "1"}),
            patch.object(channel, "_think_for_principal", side_effect=fake_think),
        ):
            await channel._handle_message(upd, ctx)

        assert agent.on_tool_start is orig_s
        assert agent.on_tool_end is orig_e

    asyncio.run(run())
