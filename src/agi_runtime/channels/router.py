"""Channel router — manages multiple messaging channels for HelloAGI.

Routes messages between platforms (CLI, HTTP, Telegram, Discord)
and the agent core. Each channel gets SRG governance equally.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from agi_runtime.channels.base import BaseChannel
from agi_runtime.core.agent import HelloAGIAgent

logger = logging.getLogger("helloagi.channels")


class ChannelRouter:
    """Manages and routes across multiple messaging channels."""

    def __init__(self, agent: HelloAGIAgent):
        self.agent = agent
        self._channels: Dict[str, BaseChannel] = {}

    def register(self, channel: BaseChannel):
        """Register a channel."""
        self._channels[channel.name] = channel
        logger.info(f"Channel registered: {channel.name}")

    async def start_all(self):
        """Start all registered channels concurrently."""
        tasks = []
        for name, channel in self._channels.items():
            logger.info(f"Starting channel: {name}")
            tasks.append(asyncio.create_task(channel.start()))
        try:
            if tasks:
                # Do not use return_exceptions=True — it hides startup failures (e.g. bad
                # token) and the process exits right after "HTTP API listening" with no trace.
                await asyncio.gather(*tasks)
            # PTB v22+: Updater.start_polling() returns once background polling is running
            # (it no longer blocks). Discord bot.start() still blocks. If every channel's
            # start() has already returned, we must keep the loop alive until Ctrl+C/cancel.
            if tasks and all(t.done() for t in tasks):
                for t in tasks:
                    if t.cancelled():
                        raise asyncio.CancelledError()
                    exc = t.exception()
                    if exc is not None:
                        raise exc
                _run_forever = asyncio.Event()
                logger.info("Channels started; waiting (Ctrl+C to stop).")
                await _run_forever.wait()
        except asyncio.CancelledError:
            raise
        finally:
            # Stops Telegram/Discord before the loop closes — avoids Windows
            # Proactor "Event loop is closed" noise during transport __del__.
            await self.stop_all()

    async def stop_all(self):
        """Stop all channels gracefully."""
        for name, channel in self._channels.items():
            try:
                await channel.stop()
                logger.info(f"Stopped channel: {name}")
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")

    def get_channel(self, name: str) -> Optional[BaseChannel]:
        """Get a channel by name."""
        return self._channels.get(name)

    @property
    def active_channels(self) -> list:
        """List active channel names."""
        return list(self._channels.keys())

    def route(self, channel: str, text: str) -> str:
        """Simple text routing (backward compatible)."""
        return f"[{channel}] {text}"
