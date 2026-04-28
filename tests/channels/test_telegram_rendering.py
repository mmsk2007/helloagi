import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from agi_runtime.channels.telegram import TelegramChannel, _TG_LIVE_MAX_PREVIEW
from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.core.agent import HelloAGIAgent


class _Msg:
    def __init__(self, text: str = ""):
        self.calls = []
        self.text = text

    async def reply_text(self, text, **kwargs):
        self.calls.append({"text": text, "kwargs": kwargs})


class _User:
    id = 1


class _Chat:
    id = 2
    type = "private"


class _Update:
    def __init__(self, text: str = ""):
        self.effective_user = _User()
        self.effective_chat = _Chat()
        self.message = _Msg(text=text)


def test_start_command_plain_text_avoids_markdown_fragility():
    settings = RuntimeSettings(
        memory_path="memory/test_identity_state.json",
        journal_path="memory/test_events.jsonl",
    )
    agent = HelloAGIAgent(settings=settings)
    channel = TelegramChannel(agent=agent, token="dummy")
    update = _Update(text="what can you do")

    asyncio.run(channel._cmd_start(update, context=None))

    assert update.message.calls
    payload = update.message.calls[0]
    assert "parse_mode" not in payload["kwargs"]
    assert "*HelloAGI" not in payload["text"]


def test_busy_telegram_principal_gets_immediate_busy_reply():
    settings = RuntimeSettings(
        memory_path="memory/test_identity_state.json",
        journal_path="memory/test_events.jsonl",
    )
    agent = HelloAGIAgent(settings=settings)
    channel = TelegramChannel(agent=agent, token="dummy")
    update = _Update(text="check the status")
    principal_id = channel._principal_id_for_update(update)
    agent.principals.update(principal_id, onboarded=True, preferred_name="Alex")
    channel._inflight_by_principal[principal_id] = {
        "started_at": time.monotonic() - 5.0,
        "preview": "check flights to DXB",
    }

    asyncio.run(channel._handle_message(update, context=None))

    assert update.message.calls
    payload = update.message.calls[0]
    assert "still working on your previous task" in payload["text"]
    assert "check flights to DXB" in payload["text"]


# ── Phase 1 robustness: live-preview safe edits, overflow split, parse fallback ──

def _make_channel() -> TelegramChannel:
    settings = RuntimeSettings(
        memory_path="memory/test_identity_state.json",
        journal_path="memory/test_events.jsonl",
    )
    agent = HelloAGIAgent(settings=settings)
    return TelegramChannel(agent=agent, token="dummy")


def _fresh_st(bot) -> dict:
    return {
        "chat_id": 42,
        "message_id": 7,
        "bot": bot,
        "debounce_s": 0.05,
        "lines": [],
        "debounce_task": None,
        "flood_strikes": 0,
        "disabled": False,
    }


class TestLivePreviewRobustness:
    def test_flood_strike_counts_disable_after_three_long_retries(self):
        """RetryAfter > 5s strikes; three strikes permanently disable the preview."""
        from telegram.error import RetryAfter

        channel = _make_channel()
        bot = MagicMock()
        bot.edit_message_text = AsyncMock(side_effect=RetryAfter(retry_after=10.0))
        st = _fresh_st(bot)

        async def run():
            for _ in range(4):
                await channel._safe_edit_text(st, "hello")

        asyncio.run(run())
        # Three strikes disable; the fourth call should short-circuit before any edit attempt.
        assert st["disabled"] is True
        assert st["flood_strikes"] == 3
        # 3 attempts before disable; no inline retry because retry_after > 5s.
        assert bot.edit_message_text.await_count == 3

    def test_short_retry_after_inline_retries_then_succeeds(self):
        """RetryAfter ≤ 5s sleeps once and retries; success on the second attempt."""
        from telegram.error import RetryAfter

        channel = _make_channel()
        bot = MagicMock()
        # First call raises RetryAfter(2s), second call succeeds.
        bot.edit_message_text = AsyncMock(
            side_effect=[RetryAfter(retry_after=0.05), None]
        )
        st = _fresh_st(bot)

        ok = asyncio.run(channel._safe_edit_text(st, "hello world"))
        assert ok is True
        assert st["flood_strikes"] == 0
        assert st["disabled"] is False
        assert bot.edit_message_text.await_count == 2

    def test_overflow_splits_into_new_message(self):
        """Pending text larger than _TG_LIVE_MAX_PREVIEW should edit head, send tail as a new message, and roll message_id."""
        channel = _make_channel()
        bot = MagicMock()
        bot.edit_message_text = AsyncMock()
        # send_message returns an object with .message_id
        new_msg = MagicMock()
        new_msg.message_id = 999
        bot.send_message = AsyncMock(return_value=new_msg)

        st = _fresh_st(bot)
        # Build content that overflows; include a newline near the end so the
        # split path picks a clean boundary.
        head = ("a" * 200 + "\n") * 14  # ~14 * 201 = 2814
        tail = "b" * 600  # adds another 600 chars → total ~3414 > 3000
        big = head + tail
        st["pending"] = big
        st["pending_for_edit"] = big

        asyncio.run(channel._live_flush_immediate(st))

        # Edit hit (with the head chunk), and a new message was sent for the tail.
        assert bot.edit_message_text.await_count >= 1
        assert bot.send_message.await_count == 1
        # Active message id rolled forward.
        assert st["message_id"] == 999
        # Lines reset to a single-element tail buffer.
        assert isinstance(st["lines"], list)
        assert len(st["lines"]) == 1
        assert "b" in st["lines"][0]
        # Sanity: the original was indeed > the live cap.
        assert len(big) > _TG_LIVE_MAX_PREVIEW

    def test_markdown_fallback_to_plain(self):
        """If HTML parse_mode trips a BadRequest about parsing, retry with plain text."""
        from telegram.error import BadRequest

        channel = _make_channel()
        bot = MagicMock()
        bot.edit_message_text = AsyncMock(
            side_effect=[BadRequest("Can't parse entities: bad tag at offset 5"), None]
        )
        st = _fresh_st(bot)

        ok = asyncio.run(channel._safe_edit_text(st, "before <bad> after"))
        assert ok is True
        assert st["flood_strikes"] == 0
        assert bot.edit_message_text.await_count == 2
        # Second call must drop parse_mode.
        second_kwargs = bot.edit_message_text.await_args_list[1].kwargs
        assert second_kwargs.get("parse_mode") is None

    def test_not_modified_is_treated_as_success(self):
        """BadRequest 'message is not modified' resets strikes and counts as success."""
        from telegram.error import BadRequest

        channel = _make_channel()
        bot = MagicMock()
        bot.edit_message_text = AsyncMock(
            side_effect=BadRequest("Bad Request: message is not modified")
        )
        st = _fresh_st(bot)
        st["flood_strikes"] = 2  # already on the brink

        ok = asyncio.run(channel._safe_edit_text(st, "hello"))
        assert ok is True
        assert st["disabled"] is False
        assert st["flood_strikes"] == 0  # reset, not incremented

    def test_disabled_state_short_circuits_edits(self):
        channel = _make_channel()
        bot = MagicMock()
        bot.edit_message_text = AsyncMock()
        st = _fresh_st(bot)
        st["disabled"] = True

        ok = asyncio.run(channel._safe_edit_text(st, "hello"))
        assert ok is False
        bot.edit_message_text.assert_not_awaited()
