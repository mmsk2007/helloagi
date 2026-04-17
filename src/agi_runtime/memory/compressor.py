"""Context compression engine.

When conversation history approaches the context limit, compresses
older turns while preserving key information. Uses an auxiliary
(cheap/fast) model for summarization.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


COMPRESSION_PROMPT = """Summarize the following conversation turns into a concise context block.
Preserve:
- The user's original goal/request
- Key decisions made
- Important results from tool executions
- Current state of the task
- What still needs to be done

Do NOT:
- Answer any questions in the conversation
- Add new information
- Make assumptions

Format:
## Context Summary
**Goal**: (what the user wants)
**Completed**: (what's been done)
**Key Results**: (important findings/outputs)
**Remaining**: (what still needs to happen)
**Active State**: (current working state)

Conversation to summarize:
{conversation}"""


class ContextCompressor:
    """Compress conversation history to fit within context limits."""

    # Approximate tokens per message (conservative estimate)
    CHARS_PER_TOKEN = 4
    # Preserve this many recent messages
    PRESERVE_RECENT = 8
    # Target size after compression (in messages)
    TARGET_MESSAGES = 15

    def __init__(self, max_context_tokens: int = 180000):
        self.max_context_tokens = max_context_tokens

    def needs_compression(self, messages: List[dict]) -> bool:
        """Check if the conversation needs compression."""
        total_chars = sum(
            len(json.dumps(m.get("content", ""), default=str))
            for m in messages
        )
        estimated_tokens = total_chars // self.CHARS_PER_TOKEN
        return estimated_tokens > (self.max_context_tokens * 0.7) or len(messages) > 30

    async def compress(self, messages: List[dict]) -> List[dict]:
        """Compress conversation history, preserving recent messages."""
        if len(messages) <= self.PRESERVE_RECENT + 2:
            return messages

        # Split: old messages to compress + recent messages to keep
        to_compress = messages[:-self.PRESERVE_RECENT]
        to_keep = messages[-self.PRESERVE_RECENT:]

        # Generate summary of old messages
        summary = await self._summarize(to_compress)

        # Build compressed history
        compressed = [
            {"role": "user", "content": f"[Context from earlier conversation]\n{summary}"},
            {"role": "assistant", "content": "I understand the context. Let me continue from where we left off."},
        ]
        compressed.extend(to_keep)

        return compressed

    async def _summarize(self, messages: List[dict]) -> str:
        """Summarize messages using LLM or heuristic fallback."""
        # Format messages for summarization
        conversation_text = self._format_messages(messages)

        if _ANTHROPIC_AVAILABLE and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                client = anthropic.Anthropic()
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",  # Use cheap/fast model
                    max_tokens=1024,
                    messages=[{
                        "role": "user",
                        "content": COMPRESSION_PROMPT.format(conversation=conversation_text[:8000]),
                    }],
                )
                return response.content[0].text
            except Exception:
                pass

        # Heuristic fallback
        return self._heuristic_summary(messages)

    def _format_messages(self, messages: List[dict]) -> str:
        """Format messages into readable text for summarization."""
        parts = []
        for m in messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if isinstance(content, str):
                parts.append(f"[{role}]: {content[:500]}")
            elif isinstance(content, list):
                # Tool results or complex content
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_result":
                            parts.append(f"[tool_result]: {str(block.get('content', ''))[:300]}")
                        elif block.get("type") == "text":
                            parts.append(f"[{role}]: {block.get('text', '')[:500]}")
        return "\n".join(parts)

    def _heuristic_summary(self, messages: List[dict]) -> str:
        """Simple heuristic compression when LLM is unavailable."""
        user_messages = [
            m.get("content", "")[:200]
            for m in messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ]
        return (
            "## Context Summary\n"
            f"**Conversation turns**: {len(messages)}\n"
            f"**User messages**: {'; '.join(user_messages[:5])}\n"
            f"**Note**: Full context was compressed to fit within limits."
        )
