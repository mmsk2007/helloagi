"""HelloAGI Sentiment & Mood Tracker — Inspired by LifeMaster.

Detects emotional tone in user messages and tracks mood over time.
This gives the agent emotional intelligence — it adapts its responses
based on how the user is feeling, not just what they're saying.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Emotion keywords for rule-based detection (fast, no API needed)
_POSITIVE_PATTERNS = {
    "happy", "great", "awesome", "excellent", "amazing", "love", "excited",
    "fantastic", "wonderful", "perfect", "thank", "thanks", "brilliant",
    "beautiful", "celebrate", "proud", "success", "accomplished", "win",
    "glad", "pleased", "thrilled", "grateful", "appreciate", "enjoy",
}

_NEGATIVE_PATTERNS = {
    "frustrated", "angry", "annoyed", "upset", "stuck", "broken", "fail",
    "failed", "error", "bug", "crash", "hate", "terrible", "awful",
    "confused", "lost", "struggling", "stressed", "overwhelmed", "tired",
    "worried", "anxious", "disappointed", "problem", "issue", "wrong",
}

_NEUTRAL_PATTERNS = {
    "how", "what", "when", "where", "why", "can", "could", "should",
    "please", "help", "show", "tell", "explain", "list", "find",
}


@dataclass
class MoodReading:
    """A single mood reading from user input."""
    sentiment: str  # "positive", "neutral", "negative"
    score: float    # -1.0 (very negative) to 1.0 (very positive)
    dominant_emotion: str  # e.g., "frustrated", "excited", "neutral"
    confidence: float  # 0.0 to 1.0


class SentimentTracker:
    """Tracks user mood across sessions.

    Stores mood history in memory/mood.json and provides:
    - Real-time sentiment detection from text
    - Mood trends over time
    - Mood-aware response guidance for the agent
    """

    def __init__(self, path: str = "memory/mood.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.history = self._load()

    def _load(self) -> list:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save(self):
        # Keep last 500 readings
        self.history = self.history[-500:]
        self.path.write_text(json.dumps(self.history, indent=2), encoding="utf-8")

    def detect(self, text: str) -> MoodReading:
        """Detect sentiment from user text using keyword analysis."""
        words = set(re.findall(r'\w+', text.lower()))

        pos_hits = words & _POSITIVE_PATTERNS
        neg_hits = words & _NEGATIVE_PATTERNS
        neu_hits = words & _NEUTRAL_PATTERNS

        pos_count = len(pos_hits)
        neg_count = len(neg_hits)
        total = pos_count + neg_count + len(neu_hits)

        if total == 0:
            return MoodReading("neutral", 0.0, "neutral", 0.3)

        # Calculate score
        if pos_count > neg_count:
            score = min(1.0, pos_count / max(total, 1))
            sentiment = "positive"
            dominant = next(iter(pos_hits)) if pos_hits else "positive"
            confidence = min(1.0, pos_count / 3)
        elif neg_count > pos_count:
            score = max(-1.0, -(neg_count / max(total, 1)))
            sentiment = "negative"
            dominant = next(iter(neg_hits)) if neg_hits else "negative"
            confidence = min(1.0, neg_count / 3)
        else:
            score = 0.0
            sentiment = "neutral"
            dominant = "neutral"
            confidence = 0.5

        return MoodReading(sentiment, round(score, 2), dominant, round(confidence, 2))

    def record(self, text: str) -> MoodReading:
        """Detect and record mood from user text."""
        reading = self.detect(text)
        entry = {
            "ts": time.time(),
            "sentiment": reading.sentiment,
            "score": reading.score,
            "dominant_emotion": reading.dominant_emotion,
            "confidence": reading.confidence,
            "text_preview": text[:100],
        }
        self.history.append(entry)
        self._save()
        return reading

    def get_current_mood(self) -> str:
        """Get the user's current mood based on recent readings."""
        if not self.history:
            return "unknown"
        # Average last 5 readings
        recent = self.history[-5:]
        avg_score = sum(r["score"] for r in recent) / len(recent)
        if avg_score > 0.3:
            return "positive"
        elif avg_score < -0.3:
            return "negative"
        return "neutral"

    def get_mood_trend(self) -> str:
        """Get mood trend (improving, declining, stable)."""
        if len(self.history) < 3:
            return "stable"

        recent = [r["score"] for r in self.history[-5:]]
        older = [r["score"] for r in self.history[-10:-5]] if len(self.history) >= 10 else [0.0]

        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        diff = recent_avg - older_avg

        if diff > 0.2:
            return "improving"
        elif diff < -0.2:
            return "declining"
        return "stable"

    def get_mood_guidance(self) -> str:
        """Get response guidance based on current mood and trend."""
        mood = self.get_current_mood()
        trend = self.get_mood_trend()

        if mood == "negative" and trend == "declining":
            return (
                "The user seems frustrated or stressed. Be extra supportive: "
                "acknowledge the difficulty, break tasks into smaller steps, "
                "celebrate small wins. Keep responses concise and practical."
            )
        elif mood == "negative":
            return (
                "The user may be dealing with a challenge. Be patient and empathetic. "
                "Offer clear solutions and alternatives when something fails."
            )
        elif mood == "positive" and trend == "improving":
            return (
                "The user is in great spirits and gaining momentum! "
                "Match their energy, suggest ambitious next steps, "
                "and build on their enthusiasm."
            )
        elif mood == "positive":
            return (
                "The user is in a good mood. Keep things efficient and positive. "
                "Encourage their progress naturally."
            )
        return ""

    def get_summary(self) -> str:
        """Get a formatted mood summary."""
        if not self.history:
            return "No mood data yet."

        mood = self.get_current_mood()
        trend = self.get_mood_trend()
        total = len(self.history)

        pos_count = sum(1 for r in self.history if r["sentiment"] == "positive")
        neg_count = sum(1 for r in self.history if r["sentiment"] == "negative")
        neu_count = total - pos_count - neg_count

        icons = {"positive": "😊", "negative": "😔", "neutral": "😐", "unknown": "❓"}
        trend_icons = {"improving": "📈", "declining": "📉", "stable": "➡️"}

        return (
            f"Current mood: {icons.get(mood, '❓')} {mood} | Trend: {trend_icons.get(trend, '➡️')} {trend}\n"
            f"History: {pos_count} positive, {neu_count} neutral, {neg_count} negative ({total} total readings)"
        )
