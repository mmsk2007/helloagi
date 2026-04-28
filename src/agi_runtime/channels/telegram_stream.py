"""Telegram-side consumer for live token streaming.

Bridges the agent's synchronous ``on_stream(delta)`` callback (invoked from
the agent worker thread that runs ``HelloAGIAgent.think``) onto the PTB
asyncio event loop.

Design mirrors Hermes's ``GatewayStreamConsumer`` but reuses the existing
HelloAGI Telegram primitives (``_markdownish_to_html``, the
``_TG_LIVE_MAX_PREVIEW`` cap, the PTB error classes used by
``TelegramChannel._safe_edit_text``-style flood control) instead of
introducing a parallel adapter abstraction.

Lifecycle:
    consumer = TelegramStreamConsumer(bot=..., chat_id=..., message_id=...,
                                      loop=event_loop)
    drain_task = asyncio.create_task(consumer.run())
    agent.on_stream = consumer.on_delta      # str => append delta;  None => segment break
    ...
    consumer.finish()                        # signal drain to flush + return
    await drain_task

The cursor character (`` ▉``) is appended to in-flight edits and stripped
from the last edit of each segment (and the final edit overall).
"""

from __future__ import annotations

import asyncio
import logging
import queue
import time
from typing import Any, Optional

logger = logging.getLogger("helloagi.telegram.stream")

# Cursor character appended while a message is still streaming. Stripped on
# finalize (segment break / consumer.finish()).
_CURSOR = " ▉"

# Maximum on-screen preview before we split into a new message — kept in sync
# with TelegramChannel's _TG_LIVE_MAX_PREVIEW.
_DEFAULT_MAX_CHARS = 3000

# Telegram hard text limit, with a small safety margin.
_TG_TEXT_LIMIT = 4096

# Edit cadence: don't fire a Telegram edit more than once per this interval
# unless the buffer crossed the byte threshold below.
_DEFAULT_EDIT_INTERVAL_S = 0.55

# Append-this-many bytes-since-last-edit forces a flush even if the timer
# hasn't elapsed (so a long token burst doesn't sit idle).
_DEFAULT_BUFFER_THRESHOLD = 40

# After this many consecutive Telegram failures we permanently disable the
# consumer — same convention as ``TelegramChannel._safe_edit_text``.
_MAX_FLOOD_STRIKES = 3


# Sentinel objects for the queue. Distinct from ``None`` (which is the
# segment-break signal) and from any user-provided string.
class _Sentinel:
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<{self.name}>"


_SEGMENT_BREAK = _Sentinel("segment_break")
_DONE = _Sentinel("done")


def _markdownish_to_html_lazy(text: str) -> str:
    """Reuse TelegramChannel's formatter without an import cycle."""
    from agi_runtime.channels.telegram import _markdownish_to_html
    return _markdownish_to_html(text)


class TelegramStreamConsumer:
    """Drain agent-thread deltas into live Telegram message edits.

    Thread-safety: ``on_delta()`` and ``finish()`` are safe to call from any
    thread. ``run()`` must be awaited on the PTB event loop ``self._loop``.
    """

    def __init__(
        self,
        *,
        bot: Any,
        chat_id: int,
        message_id: int,
        loop: asyncio.AbstractEventLoop,
        max_chars: int = _DEFAULT_MAX_CHARS,
        edit_interval_s: float = _DEFAULT_EDIT_INTERVAL_S,
        buffer_threshold: int = _DEFAULT_BUFFER_THRESHOLD,
    ) -> None:
        self._bot = bot
        self._chat_id = int(chat_id)
        self._message_id: Optional[int] = int(message_id)
        self._loop = loop
        self._max_chars = max_chars
        self._edit_interval_s = edit_interval_s
        self._buffer_threshold = buffer_threshold

        # Thread-safe queue. We *intentionally* use queue.Queue (not
        # asyncio.Queue) because on_delta is called from the agent worker
        # thread, not the event loop.
        self._q: "queue.Queue[Any]" = queue.Queue()

        self._segment_text: str = ""    # text in the currently-active message
        self._dirty_since_edit: int = 0
        self._last_edit_t: float = 0.0
        self._flood_strikes: int = 0
        self._current_interval_s: float = edit_interval_s
        self._disabled: bool = False
        self._done: bool = False

    # ── Producer-side API (agent thread) ───────────────────────

    def on_delta(self, text: Optional[str]) -> None:
        """Receive a token delta (or segment-break sentinel)."""
        if self._done:
            return
        if text is None:
            self._q.put(_SEGMENT_BREAK)
        else:
            # Empty deltas are harmless but waste a queue slot — drop them.
            if text:
                self._q.put(text)

    def finish(self) -> None:
        """Signal the drain loop to flush + exit. Safe to call multiple times."""
        if self._done:
            return
        self._q.put(_DONE)

    # ── Consumer-side: async drain loop ────────────────────────

    async def run(self) -> None:
        """Drain the queue, applying cadence and overflow rules."""
        try:
            while True:
                got_any, hit_segment, hit_done = await self._drain_available()
                now = time.monotonic()
                # Decide whether to fire an edit this tick.
                must_edit = hit_segment or hit_done or self._segment_overflow_pending()
                want_edit = (
                    got_any
                    and (
                        (now - self._last_edit_t) >= self._current_interval_s
                        or self._dirty_since_edit >= self._buffer_threshold
                    )
                )
                if must_edit or want_edit:
                    await self._flush_edit(finalize=hit_segment or hit_done)
                    self._last_edit_t = time.monotonic()
                    self._dirty_since_edit = 0

                if hit_segment:
                    self._open_new_segment()

                if hit_done:
                    return

                # Nothing to do — yield briefly. Use a short sleep instead of
                # an asyncio.Event because ``on_delta`` is sync (no easy way
                # to signal an asyncio primitive across the thread boundary
                # without ``call_soon_threadsafe``, which is overkill here).
                if not got_any:
                    await asyncio.sleep(0.05)
        except Exception:
            logger.exception("TelegramStreamConsumer.run crashed")

    # ── Internals ──────────────────────────────────────────────

    async def _drain_available(self) -> tuple[bool, bool, bool]:
        """Pull everything available off the queue without blocking.

        Returns (got_any_text, saw_segment_break, saw_done).
        """
        got_any = False
        hit_segment = False
        hit_done = False
        # Cap drained items per tick so a runaway producer can't starve the
        # cadence logic.
        for _ in range(256):
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            if item is _DONE:
                hit_done = True
                self._done = True
                break
            if item is _SEGMENT_BREAK:
                hit_segment = True
                # Stop draining at the boundary so the segment is finalized
                # before we accept text into the *next* segment.
                break
            if isinstance(item, str):
                self._segment_text += item
                self._dirty_since_edit += len(item)
                got_any = True
        return got_any, hit_segment, hit_done

    def _segment_overflow_pending(self) -> bool:
        return len(self._segment_text) > self._max_chars

    def _open_new_segment(self) -> None:
        """Start a fresh message for the next chunk of streamed text."""
        self._segment_text = ""
        self._message_id = None  # force send_message on next flush
        self._dirty_since_edit = 0

    async def _flush_edit(self, *, finalize: bool) -> None:
        """Render the in-flight segment to Telegram (edit or send)."""
        if self._disabled:
            return

        text = self._segment_text
        if not text:
            return

        # Overflow handling: split — finalize the current message with the
        # head, then move the tail into a fresh message that we'll keep
        # editing.
        if len(text) > self._max_chars:
            await self._split_and_roll(text)
            return

        body = text if not finalize else text  # cursor handled below
        # Append cursor when still in-flight; strip when finalizing.
        if not finalize:
            body = body + _CURSOR
        # Hard text-limit safety (we should never hit this thanks to the
        # max_chars split, but defend anyway).
        if len(body) > _TG_TEXT_LIMIT:
            body = body[: _TG_TEXT_LIMIT - 8] + "\n…(trimmed)"

        if self._message_id is None:
            await self._send_new(body)
        else:
            await self._edit(body)

    async def _split_and_roll(self, text: str) -> None:
        """Edit current message with head; send tail as fresh message."""
        limit = self._max_chars
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        head = text[:cut].rstrip()
        tail = text[cut:].lstrip("\n")
        if not tail:
            await self._edit(head)
            return

        # Finalize the head in the current message (no cursor).
        if self._message_id is not None:
            await self._edit(head)
        else:
            # No active message yet — send head as new, then tail as new.
            await self._send_new(head)

        if self._disabled:
            return

        # Open a new message that will continue receiving deltas, with a
        # cursor since we're still in-flight.
        body = tail + _CURSOR
        if len(body) > _TG_TEXT_LIMIT:
            body = body[: _TG_TEXT_LIMIT - 8] + "\n…(trimmed)"
        await self._send_new(body)
        # Reset the in-flight buffer to just the tail (without cursor) so
        # the next delta appends correctly.
        self._segment_text = tail

    async def _send_new(self, body: str) -> None:
        """Open a new Telegram message and remember its id for edits."""
        if self._disabled:
            return
        try:
            msg = await self._bot.send_message(
                chat_id=self._chat_id,
                text=_markdownish_to_html_lazy(body),
                parse_mode="HTML",
            )
            self._message_id = msg.message_id
            self._reset_strikes()
        except Exception as exc:
            logger.debug("stream consumer send (HTML) failed: %s — retrying plain", exc)
            try:
                msg = await self._bot.send_message(chat_id=self._chat_id, text=body)
                self._message_id = msg.message_id
                self._reset_strikes()
            except Exception as exc2:
                logger.debug("stream consumer send (plain) failed: %s", exc2)
                self._strike(f"send: {exc2}")

    async def _edit(self, body: str) -> None:
        """Edit the active message with HTML→plain fallback + flood control."""
        if self._disabled or self._message_id is None:
            return
        try:
            from telegram.error import BadRequest, RetryAfter
        except Exception:
            self._disabled = True
            return

        html_body = _markdownish_to_html_lazy(body)
        for attempt in range(2):
            try:
                await self._bot.edit_message_text(
                    chat_id=self._chat_id,
                    message_id=self._message_id,
                    text=html_body,
                    parse_mode="HTML",
                )
                self._reset_strikes()
                return
            except RetryAfter as e:
                wait = float(getattr(e, "retry_after", 0.0) or 0.0)
                if wait <= 5.0 and attempt == 0:
                    await asyncio.sleep(max(wait, 0.1))
                    continue
                # Long backoff: bump our cadence too, so we'll naturally
                # ease off Telegram even if the strikes haven't capped yet.
                self._current_interval_s = min(self._current_interval_s * 2.0, 10.0)
                self._strike(f"RetryAfter {wait:.1f}s")
                return
            except BadRequest as e:
                emsg = str(e).lower()
                if "message is not modified" in emsg:
                    self._reset_strikes()
                    return
                if "parse" in emsg or "entity" in emsg or "tag" in emsg:
                    try:
                        await self._bot.edit_message_text(
                            chat_id=self._chat_id,
                            message_id=self._message_id,
                            text=body,
                            parse_mode=None,
                        )
                        self._reset_strikes()
                    except Exception as ex2:
                        logger.debug("stream consumer plain fallback failed: %s", ex2)
                        self._strike(f"plain fallback: {ex2}")
                    return
                self._strike(f"BadRequest: {e}")
                return
            except Exception as e:
                logger.debug("stream consumer edit failed: %s", e)
                self._strike(str(e))
                return

    def _strike(self, reason: str) -> None:
        self._flood_strikes += 1
        if self._flood_strikes >= _MAX_FLOOD_STRIKES:
            self._disabled = True
            logger.info(
                "TelegramStreamConsumer disabled after %d strikes (%s)",
                _MAX_FLOOD_STRIKES, reason,
            )

    def _reset_strikes(self) -> None:
        self._flood_strikes = 0
        self._current_interval_s = self._edit_interval_s

    # ── Test / introspection helpers ───────────────────────────

    @property
    def disabled(self) -> bool:
        return self._disabled

    @property
    def message_id(self) -> Optional[int]:
        return self._message_id

    @property
    def flood_strikes(self) -> int:
        return self._flood_strikes
