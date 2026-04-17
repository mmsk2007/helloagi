"""HelloAGI Context Compiler — Inspired by LifeMaster's contextCompiler.

Compiles a unified context object from ALL available data sources about the user.
This is what makes the agent feel truly intelligent — it knows everything relevant
about the user and their current situation when responding.

Sources compiled:
- Identity (name, character, purpose)
- Growth data (streaks, milestones, sessions)
- Mood/sentiment (current mood, trend)
- Environment (OS, time, working directory)
- Recent interactions (last N messages)
- Skills (learned capabilities)
- Active tools (available capabilities)
- Memory (stored facts and preferences)
"""

from __future__ import annotations

import os
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class CompiledContext:
    """A unified context snapshot of everything the agent knows."""

    # User identity
    user_name: str = ""
    agent_name: str = ""
    agent_character: str = ""

    # Temporal context
    time_of_day: str = ""
    day_of_week: str = ""
    date: str = ""
    energy_level: str = ""

    # Emotional context
    current_mood: str = "unknown"
    mood_trend: str = "stable"
    mood_guidance: str = ""

    # Growth context
    session_count: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    total_tool_calls: int = 0
    skills_learned: int = 0
    milestones: list = field(default_factory=list)

    # Environment context
    os_name: str = ""
    python_version: str = ""
    working_directory: str = ""
    has_api_key: bool = False

    # Session context
    messages_this_session: int = 0
    tools_used_this_session: list = field(default_factory=list)

    # Memory context
    recent_memories: list = field(default_factory=list)
    known_preferences: list = field(default_factory=list)

    # Skills context
    available_skills: list = field(default_factory=list)

    def to_prompt(self) -> str:
        """Convert compiled context to a system prompt section."""
        parts = []

        # Temporal awareness
        parts.append(f"Current time: {self.time_of_day}, {self.day_of_week} {self.date}")
        if self.energy_level:
            parts.append(f"Expected user energy: {self.energy_level}")

        # Emotional intelligence
        if self.current_mood != "unknown":
            parts.append(f"User's current mood: {self.current_mood} (trend: {self.mood_trend})")
        if self.mood_guidance:
            parts.append(f"Response guidance: {self.mood_guidance}")

        # Relationship depth
        if self.session_count > 0:
            parts.append(f"Relationship: {self.session_count} sessions together, {self.current_streak}-day streak")
        if self.milestones:
            parts.append(f"Achievements: {len(self.milestones)} milestones reached")

        # Environment awareness
        parts.append(f"Environment: {self.os_name}, Python {self.python_version}")
        if self.working_directory:
            parts.append(f"Working in: {self.working_directory}")

        # Memory
        if self.recent_memories:
            parts.append("Recent memories: " + "; ".join(self.recent_memories[:5]))

        # Skills
        if self.available_skills:
            parts.append(f"Available skills: {', '.join(self.available_skills[:10])}")

        return "\n".join(parts)

    def to_dict(self) -> dict:
        """Serialize for storage or API response."""
        return {
            "user_name": self.user_name,
            "agent_name": self.agent_name,
            "time_of_day": self.time_of_day,
            "day_of_week": self.day_of_week,
            "current_mood": self.current_mood,
            "mood_trend": self.mood_trend,
            "session_count": self.session_count,
            "current_streak": self.current_streak,
            "skills_learned": self.skills_learned,
            "os_name": self.os_name,
            "messages_this_session": self.messages_this_session,
        }


class ContextCompiler:
    """Compiles a unified context from all data sources.

    Inspired by LifeMaster's contextCompiler which pulls from 12+ sources
    to build a complete picture of the user's current state.
    """

    def compile(
        self,
        identity=None,
        growth=None,
        sentiment=None,
        skills=None,
        session_messages: int = 0,
        session_tools: list = None,
    ) -> CompiledContext:
        """Compile context from all available sources."""
        ctx = CompiledContext()

        # Temporal context
        now = datetime.now()
        hour = now.hour
        ctx.date = now.strftime("%Y-%m-%d")
        ctx.day_of_week = now.strftime("%A")

        if 5 <= hour < 12:
            ctx.time_of_day = "morning"
            ctx.energy_level = "high"
        elif 12 <= hour < 17:
            ctx.time_of_day = "afternoon"
            ctx.energy_level = "medium"
        elif 17 <= hour < 21:
            ctx.time_of_day = "evening"
            ctx.energy_level = "medium"
        else:
            ctx.time_of_day = "night"
            ctx.energy_level = "low"

        # Identity
        if identity:
            state = identity.state if hasattr(identity, "state") else identity
            ctx.agent_name = getattr(state, "name", "")
            ctx.agent_character = getattr(state, "character", "")

        # Growth data
        if growth:
            data = growth.data if hasattr(growth, "data") else {}
            ctx.session_count = data.get("total_sessions", 0)
            ctx.current_streak = data.get("current_streak", 0)
            ctx.longest_streak = data.get("longest_streak", 0)
            ctx.total_tool_calls = data.get("total_tool_calls", 0)
            ctx.skills_learned = data.get("skills_learned", 0)
            ctx.milestones = data.get("milestones", [])

        # Sentiment / mood
        if sentiment:
            ctx.current_mood = sentiment.get_current_mood()
            ctx.mood_trend = sentiment.get_mood_trend()
            ctx.mood_guidance = sentiment.get_mood_guidance()

        # Skills
        if skills:
            try:
                skill_list = skills.list_skills() if hasattr(skills, "list_skills") else []
                ctx.available_skills = [s.get("name", "") for s in skill_list]
            except Exception:
                pass

        # Environment
        ctx.os_name = platform.system()
        ctx.python_version = platform.python_version()
        ctx.working_directory = os.getcwd()
        ctx.has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

        # Session
        ctx.messages_this_session = session_messages
        ctx.tools_used_this_session = session_tools or []

        return ctx
