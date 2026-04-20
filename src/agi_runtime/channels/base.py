"""Base channel interface for HelloAGI messaging platforms.

All channels (CLI, HTTP, Telegram, Discord) implement this interface
to provide a consistent gateway pattern.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Optional


@dataclass
class ChannelMessage:
    """Inbound message from any channel."""
    text: str
    user_id: str
    channel_id: str
    channel_type: str  # "cli", "http", "telegram", "discord"
    timestamp: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)


@dataclass
class ChannelResponse:
    """Outbound response to any channel."""
    text: str
    channel_id: str
    decision: str = "allow"
    risk: float = 0.0
    tool_calls: int = 0
    metadata: Dict = field(default_factory=dict)


class BaseChannel(ABC):
    """Abstract base class for all messaging channels.

    Each channel:
    1. Receives messages from its platform
    2. Routes through the agent
    3. Sends responses back
    4. Manages per-user sessions
    5. Declares its outbound capabilities so tools can negotiate
    """

    # Capability tags. Concrete channels override to advertise what they can deliver.
    # Tools query this via get_tool_context_value("channel").capabilities to decide
    # whether to attempt a media send or fall back to text.
    capabilities: FrozenSet[str] = frozenset({"text"})

    def __init__(self, name: str):
        self.name = name
        self._sessions: Dict[str, list] = {}  # user_id -> message history

    @abstractmethod
    async def start(self):
        """Start listening for messages."""
        ...

    @abstractmethod
    async def stop(self):
        """Stop the channel gracefully."""
        ...

    @abstractmethod
    async def send(self, channel_id: str, text: str, **kwargs):
        """Send a message to a channel/user."""
        ...

    async def send_file(
        self,
        channel_id: str,
        path: str,
        caption: str = "",
        filename: str = "",
    ) -> Dict[str, Any]:
        """Send a file/document attachment. Override in channels that support it.

        Return shape: {"ok": bool, "message_id": str | None, "error": str | None}.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support file attachments"
        )

    async def send_image(
        self,
        channel_id: str,
        path_or_url: str,
        caption: str = "",
    ) -> Dict[str, Any]:
        """Send an image. Accepts a local path or http(s) URL. Override per-channel."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support image attachments"
        )

    async def send_voice(
        self,
        channel_id: str,
        path: str,
        caption: str = "",
    ) -> Dict[str, Any]:
        """Send a voice message (e.g. OGG/Opus). Override per-channel."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support voice attachments"
        )

    def get_session(self, user_id: str) -> list:
        """Get or create a session for a user."""
        if user_id not in self._sessions:
            self._sessions[user_id] = []
        return self._sessions[user_id]

    def clear_session(self, user_id: str):
        """Clear a user's session history."""
        self._sessions.pop(user_id, None)
