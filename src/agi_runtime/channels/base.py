"""Base channel interface for HelloAGI messaging platforms.

All channels (CLI, HTTP, Telegram, Discord) implement this interface
to provide a consistent gateway pattern.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional


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
    """

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

    def get_session(self, user_id: str) -> list:
        """Get or create a session for a user."""
        if user_id not in self._sessions:
            self._sessions[user_id] = []
        return self._sessions[user_id]

    def clear_session(self, user_id: str):
        """Clear a user's session history."""
        self._sessions.pop(user_id, None)
