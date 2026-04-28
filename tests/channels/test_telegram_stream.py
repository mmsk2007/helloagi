"""Tests for the TelegramStreamConsumer (Phase 2 token streaming)."""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from agi_runtime.channels.telegram_stream import TelegramStreamConsumer


def _fake_send_msg(message_id: int):
    msg = MagicMock()
    msg.message_id = message_id
    return msg


async def _drive(consumer: TelegramStreamConsumer, deltas: List[Optional[str]], *,
                 finish: bool = True, settle_ms: int = 200) -> None:
    """Run the consumer, feed deltas, finish, and await drain."""
    task = asyncio.create_task(consumer.run())
    try:
        # Give the loop a tick to enter run()
        await asyncio.sleep(0)
        for d in deltas:
            consumer.on_delta(d)
            # Let the consumer drain between deltas so cadence + segment-break
            # logic actually plays out (rather than batching everything).
            await asyncio.sleep(0.06)
        if finish:
            consumer.finish()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except Exception:
                pass


def _make_bot(send_message_ids: List[int]):
    bot = MagicMock()
    msgs = iter(send_message_ids)
    bot.send_message = AsyncMock(side_effect=lambda **kw: _fake_send_msg(next(msgs)))
    bot.edit_message_text = AsyncMock()
    return bot


def test_consumer_drains_deltas_into_edits():
    bot = _make_bot([])
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    consumer = TelegramStreamConsumer(
        bot=bot, chat_id=42, message_id=7, loop=loop,
        edit_interval_s=0.0, buffer_threshold=1,
    )

    async def go():
        await _drive(consumer, ["Hello, ", "world", "!"])

    try:
        loop.run_until_complete(go())
    finally:
        loop.close()

    assert bot.edit_message_text.await_count >= 1
    # Last edit body must contain the full streamed text.
    last_kwargs = bot.edit_message_text.await_args_list[-1].kwargs
    text = last_kwargs.get("text", "")
    assert "Hello, world!" in text
    # Cursor stripped on finalize.
    assert not text.rstrip().endswith("▉")


def test_segment_break_starts_new_message():
    bot = _make_bot([100, 200])
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    consumer = TelegramStreamConsumer(
        bot=bot, chat_id=42, message_id=7, loop=loop,
        edit_interval_s=0.0, buffer_threshold=1,
    )

    async def go():
        await _drive(consumer, ["abc", None, "def"])

    try:
        loop.run_until_complete(go())
    finally:
        loop.close()

    # A new message must have been opened for the post-break segment.
    assert bot.send_message.await_count >= 1
    # Final message id should be the most recent send_message id.
    assert consumer.message_id == 100  # only one new send (for "def")


def test_finish_strips_cursor_on_final_edit():
    bot = _make_bot([])
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    consumer = TelegramStreamConsumer(
        bot=bot, chat_id=1, message_id=1, loop=loop,
        edit_interval_s=0.0, buffer_threshold=1,
    )

    async def go():
        await _drive(consumer, ["streaming", " text"])

    try:
        loop.run_until_complete(go())
    finally:
        loop.close()

    # Inspect the *last* edit payload: must not end with the cursor glyph.
    last_kwargs = bot.edit_message_text.await_args_list[-1].kwargs
    body = last_kwargs.get("text", "")
    assert "▉" not in body  # finalize stripped the cursor


def test_overflow_splits_streamed_text_into_two_messages():
    bot = _make_bot([777])
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    consumer = TelegramStreamConsumer(
        bot=bot, chat_id=1, message_id=1, loop=loop,
        max_chars=100,           # tiny cap so we trigger split easily
        edit_interval_s=0.0,
        buffer_threshold=1,
    )

    chunk = "a" * 60 + "\n" + "b" * 60  # 121 chars, > max_chars=100
    async def go():
        await _drive(consumer, [chunk])

    try:
        loop.run_until_complete(go())
    finally:
        loop.close()

    # Head edited on the original (id=1), tail sent as new message (id=777).
    assert bot.edit_message_text.await_count >= 1
    assert bot.send_message.await_count == 1
    assert consumer.message_id == 777


def test_flood_disables_after_three_strikes():
    from telegram.error import RetryAfter

    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=_fake_send_msg(99))
    bot.edit_message_text = AsyncMock(side_effect=RetryAfter(retry_after=10.0))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    consumer = TelegramStreamConsumer(
        bot=bot, chat_id=1, message_id=1, loop=loop,
        edit_interval_s=0.0, buffer_threshold=1,
    )

    async def go():
        # Five deltas should be plenty to accrue three strikes.
        await _drive(consumer, ["a", "b", "c", "d", "e"])

    try:
        loop.run_until_complete(go())
    finally:
        loop.close()

    assert consumer.disabled is True
    assert consumer.flood_strikes >= 3


def test_short_retry_after_inline_retries_then_succeeds():
    from telegram.error import RetryAfter

    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=_fake_send_msg(99))
    # First edit raises a tiny RetryAfter; second succeeds.
    bot.edit_message_text = AsyncMock(
        side_effect=[RetryAfter(retry_after=0.05), None, None, None, None, None]
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    consumer = TelegramStreamConsumer(
        bot=bot, chat_id=1, message_id=1, loop=loop,
        edit_interval_s=0.0, buffer_threshold=1,
    )

    async def go():
        await _drive(consumer, ["hello"])

    try:
        loop.run_until_complete(go())
    finally:
        loop.close()

    assert consumer.disabled is False
    assert consumer.flood_strikes == 0
