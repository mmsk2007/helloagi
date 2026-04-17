"""HelloAGI Personality Engine — Makes the agent feel alive and human.

Inspired by LifeMaster's emotional intelligence and personalization.
Provides time-aware greetings, growth tracking, session streaks,
and personality warmth that evolves with the user.
"""

from __future__ import annotations

import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


def get_time_greeting() -> tuple:
    """Get time-appropriate greeting with energy level and icon.

    Returns (greeting, energy_level, icon)
    """
    hour = datetime.now().hour

    if 5 <= hour < 8:
        return "Good morning, early riser", "high", "🌅"
    elif 8 <= hour < 12:
        return "Good morning", "high", "☀️"
    elif 12 <= hour < 14:
        return "Good afternoon", "medium", "🌤️"
    elif 14 <= hour < 17:
        return "Good afternoon", "medium", "⛅"
    elif 17 <= hour < 20:
        return "Good evening", "medium", "🌆"
    elif 20 <= hour < 23:
        return "Good evening", "low", "🌙"
    else:
        return "Burning the midnight oil", "low", "🌃"


class GrowthTracker:
    """Tracks user interaction streaks and growth milestones.

    Stores in memory/growth.json:
    - Session streak (consecutive days)
    - Longest streak
    - Total sessions
    - Total tool calls
    - Skills learned
    - Milestones achieved
    """

    def __init__(self, path: str = "memory/growth.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "current_streak": 0,
            "longest_streak": 0,
            "total_sessions": 0,
            "total_tool_calls": 0,
            "total_messages": 0,
            "skills_learned": 0,
            "last_session_date": "",
            "first_session_date": "",
            "milestones": [],
        }

    def _save(self):
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def record_session(self):
        """Record a new session and update streaks."""
        today = datetime.now().strftime("%Y-%m-%d")
        last = self.data.get("last_session_date", "")

        if not self.data.get("first_session_date"):
            self.data["first_session_date"] = today

        if last == today:
            # Already recorded today
            return

        yesterday = datetime.now()
        from datetime import timedelta
        yesterday_str = (yesterday - timedelta(days=1)).strftime("%Y-%m-%d")

        if last == yesterday_str:
            # Consecutive day — extend streak
            self.data["current_streak"] += 1
        elif last != today:
            # Streak broken — reset
            self.data["current_streak"] = 1

        self.data["total_sessions"] += 1
        self.data["last_session_date"] = today

        if self.data["current_streak"] > self.data["longest_streak"]:
            self.data["longest_streak"] = self.data["current_streak"]

        # Check milestones
        self._check_milestones()
        self._save()

    def record_tool_call(self):
        self.data["total_tool_calls"] = self.data.get("total_tool_calls", 0) + 1

    def record_message(self):
        self.data["total_messages"] = self.data.get("total_messages", 0) + 1

    def record_skill_learned(self):
        self.data["skills_learned"] = self.data.get("skills_learned", 0) + 1

    def _check_milestones(self):
        milestones = self.data.get("milestones", [])
        achieved = set(milestones)

        checks = [
            (self.data["total_sessions"] >= 1, "first_session", "First session! The journey begins."),
            (self.data["total_sessions"] >= 10, "10_sessions", "10 sessions! You're building a habit."),
            (self.data["total_sessions"] >= 50, "50_sessions", "50 sessions! A true power user."),
            (self.data["total_sessions"] >= 100, "100_sessions", "100 sessions! Your agent knows you deeply."),
            (self.data["current_streak"] >= 3, "3_day_streak", "3-day streak! Consistency is key."),
            (self.data["current_streak"] >= 7, "7_day_streak", "7-day streak! A full week of AGI."),
            (self.data["current_streak"] >= 30, "30_day_streak", "30-day streak! A month of growth."),
            (self.data.get("total_tool_calls", 0) >= 100, "100_tools", "100 tool calls! Serious automation."),
            (self.data.get("skills_learned", 0) >= 5, "5_skills", "5 skills learned! Your agent is evolving."),
        ]

        for condition, key, msg in checks:
            if condition and key not in achieved:
                milestones.append(key)

        self.data["milestones"] = milestones

    def get_streak_message(self) -> str:
        """Get a motivational message based on current streak."""
        streak = self.data.get("current_streak", 0)

        if streak >= 30:
            return f"🏆 {streak}-day streak! Incredible dedication. You're unstoppable!"
        elif streak >= 14:
            return f"🔥 {streak}-day streak! Two weeks of consistent growth!"
        elif streak >= 7:
            return f"⭐ {streak}-day streak! A full week of building with AGI!"
        elif streak >= 3:
            return f"💪 {streak}-day streak! You're building an excellent habit!"
        elif streak >= 1:
            return f"✨ Day {streak}! Every journey begins with a single step."
        else:
            return "Welcome back! Let's pick up where we left off."

    def get_growth_summary(self) -> str:
        """Get a formatted growth summary."""
        d = self.data
        parts = [
            f"Sessions: {d.get('total_sessions', 0)} | Streak: {d.get('current_streak', 0)} days",
            f"Longest streak: {d.get('longest_streak', 0)} days",
            f"Messages: {d.get('total_messages', 0)} | Tool calls: {d.get('total_tool_calls', 0)}",
            f"Skills learned: {d.get('skills_learned', 0)}",
        ]

        milestones = d.get("milestones", [])
        if milestones:
            parts.append(f"Milestones: {len(milestones)} achieved")

        return "\n".join(parts)

    def get_new_milestones(self) -> list:
        """Get recently achieved milestones (since last check)."""
        # Simple: return all milestones for now
        return self.data.get("milestones", [])


def build_personality_prompt(
    identity_name: str,
    identity_character: str,
    owner_name: str = "",
    growth: Optional[GrowthTracker] = None,
) -> str:
    """Build personality-aware system prompt additions.

    Makes the agent feel alive: addresses user directly, references
    their growth, adapts tone to time of day.
    """
    greeting, energy, icon = get_time_greeting()
    parts = []

    # Direct address — never say "the user"
    parts.append(
        "IMPORTANT: Always address the person directly using 'you' and 'your'. "
        "Never say 'the user' or 'the person'. You are their dedicated AI partner."
    )

    # Time awareness
    parts.append(f"Current time context: {greeting} ({icon}). User energy level is likely {energy}.")

    if energy == "high":
        parts.append("This is a good time for challenging tasks and deep work.")
    elif energy == "low":
        parts.append("Be mindful that energy may be lower — prioritize clarity and efficiency.")

    # Personal relationship
    if owner_name:
        parts.append(f"You are working with {owner_name}. Use their name occasionally to feel personal.")

    # Growth awareness
    if growth:
        streak = growth.data.get("current_streak", 0)
        total = growth.data.get("total_sessions", 0)

        if streak > 1:
            parts.append(f"This person is on a {streak}-day streak with you. Acknowledge their consistency.")
        if total > 10:
            parts.append(f"You've had {total} sessions together. You know each other well — be direct and efficient.")
        elif total > 1:
            parts.append(f"You've had {total} sessions together. You're building a working relationship.")

    # Personality warmth
    parts.append(
        "Be warm but not overly enthusiastic. Show genuine interest in their goals. "
        "Celebrate wins naturally. If they're struggling, be supportive and practical."
    )

    return "\n".join(parts)
