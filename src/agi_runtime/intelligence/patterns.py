"""HelloAGI Behavioral Pattern Detector — Inspired by LifeMaster.

Detects usage patterns and behavioral trends to make the agent smarter:
- Peak activity hours (when the user is most active)
- Preferred tools (what tools the user triggers most)
- Task categories (what kind of work the user does)
- Session duration trends
- Topic clustering (what subjects come up repeatedly)

This is what separates AGI from a chatbot — the agent LEARNS from patterns.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class UserPattern:
    """Detected pattern about the user."""
    pattern_type: str  # "peak_hours", "preferred_tools", "task_focus", etc.
    description: str
    confidence: float  # 0.0 to 1.0
    data: dict


class PatternDetector:
    """Detects behavioral patterns from usage data.

    Analyzes interaction history to discover:
    - When the user is most active
    - What tools they use most
    - What topics come up repeatedly
    - How their usage is evolving
    """

    def __init__(self, path: str = "memory/patterns.json"):
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
            "interactions": [],  # [{ts, hour, tools, topic_words, duration_s}]
            "detected_patterns": [],
        }

    def _save(self):
        # Keep last 1000 interactions
        self.data["interactions"] = self.data["interactions"][-1000:]
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def record_interaction(
        self,
        user_text: str,
        tools_used: list = None,
        duration_s: float = 0,
    ):
        """Record an interaction for pattern analysis."""
        now = datetime.now()
        # Extract topic words (simple: nouns and verbs over 4 chars)
        words = [w.lower() for w in user_text.split() if len(w) > 4 and w.isalpha()]

        entry = {
            "ts": time.time(),
            "hour": now.hour,
            "day": now.strftime("%A"),
            "tools": tools_used or [],
            "topic_words": words[:10],
            "duration_s": duration_s,
        }
        self.data["interactions"].append(entry)
        self._save()

    def detect_patterns(self) -> list:
        """Run pattern detection on accumulated data."""
        interactions = self.data.get("interactions", [])
        if len(interactions) < 5:
            return []

        patterns = []

        # 1. Peak hours
        peak = self._detect_peak_hours(interactions)
        if peak:
            patterns.append(peak)

        # 2. Preferred tools
        tools = self._detect_preferred_tools(interactions)
        if tools:
            patterns.append(tools)

        # 3. Recurring topics
        topics = self._detect_recurring_topics(interactions)
        if topics:
            patterns.append(topics)

        # 4. Usage frequency
        freq = self._detect_usage_frequency(interactions)
        if freq:
            patterns.append(freq)

        # 5. Day preferences
        days = self._detect_day_preferences(interactions)
        if days:
            patterns.append(days)

        self.data["detected_patterns"] = [
            {"type": p.pattern_type, "desc": p.description, "confidence": p.confidence}
            for p in patterns
        ]
        self._save()
        return patterns

    def _detect_peak_hours(self, interactions: list) -> Optional[UserPattern]:
        """Find the user's most active hours."""
        hours = Counter(i["hour"] for i in interactions)
        if not hours:
            return None

        top_hours = hours.most_common(3)
        peak_hour = top_hours[0][0]
        peak_count = top_hours[0][1]
        total = sum(hours.values())

        confidence = min(1.0, peak_count / max(total * 0.15, 1))

        period = "morning" if 5 <= peak_hour < 12 else "afternoon" if 12 <= peak_hour < 17 else "evening" if 17 <= peak_hour < 21 else "night"

        return UserPattern(
            pattern_type="peak_hours",
            description=f"Most active around {peak_hour}:00 ({period})",
            confidence=round(confidence, 2),
            data={"peak_hour": peak_hour, "top_hours": [(h, c) for h, c in top_hours]},
        )

    def _detect_preferred_tools(self, interactions: list) -> Optional[UserPattern]:
        """Find the user's most-used tools."""
        all_tools = []
        for i in interactions:
            all_tools.extend(i.get("tools", []))

        if not all_tools:
            return None

        tool_counts = Counter(all_tools)
        top_tools = tool_counts.most_common(5)
        total = sum(tool_counts.values())

        return UserPattern(
            pattern_type="preferred_tools",
            description=f"Top tools: {', '.join(t for t, _ in top_tools[:3])}",
            confidence=min(1.0, total / 20),
            data={"top_tools": [(t, c) for t, c in top_tools], "total_calls": total},
        )

    def _detect_recurring_topics(self, interactions: list) -> Optional[UserPattern]:
        """Find topics that come up repeatedly."""
        all_words = []
        for i in interactions:
            all_words.extend(i.get("topic_words", []))

        if not all_words:
            return None

        word_counts = Counter(all_words)
        # Filter out very common words
        common = {"about", "would", "could", "should", "their", "there", "which", "these", "those"}
        top_words = [(w, c) for w, c in word_counts.most_common(20) if w not in common and c >= 2][:10]

        if not top_words:
            return None

        return UserPattern(
            pattern_type="recurring_topics",
            description=f"Frequent topics: {', '.join(w for w, _ in top_words[:5])}",
            confidence=min(1.0, len(top_words) / 5),
            data={"topics": [(w, c) for w, c in top_words]},
        )

    def _detect_usage_frequency(self, interactions: list) -> Optional[UserPattern]:
        """Detect how frequently the user interacts."""
        if len(interactions) < 2:
            return None

        # Calculate average gap between interactions
        timestamps = sorted(i["ts"] for i in interactions)
        gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        avg_gap = sum(gaps) / len(gaps)

        if avg_gap < 60:
            freq = "rapid-fire (multiple per minute)"
        elif avg_gap < 300:
            freq = "active session (every few minutes)"
        elif avg_gap < 3600:
            freq = "steady (every ~hour)"
        elif avg_gap < 86400:
            freq = "daily check-ins"
        else:
            freq = "occasional use"

        return UserPattern(
            pattern_type="usage_frequency",
            description=f"Usage pattern: {freq}",
            confidence=min(1.0, len(interactions) / 10),
            data={"avg_gap_seconds": round(avg_gap, 1), "total_interactions": len(interactions)},
        )

    def _detect_day_preferences(self, interactions: list) -> Optional[UserPattern]:
        """Detect preferred days of the week."""
        days = Counter(i.get("day", "") for i in interactions if i.get("day"))
        if not days:
            return None

        top_days = days.most_common(3)
        return UserPattern(
            pattern_type="day_preferences",
            description=f"Most active on: {', '.join(d for d, _ in top_days[:2])}",
            confidence=min(1.0, sum(c for _, c in top_days) / max(len(interactions), 1)),
            data={"day_counts": {d: c for d, c in days.items()}},
        )

    def get_insights(self) -> str:
        """Get a formatted summary of detected patterns."""
        patterns = self.detect_patterns()
        if not patterns:
            return "Not enough data yet to detect patterns. Keep using HelloAGI!"

        lines = ["Behavioral Patterns Detected:"]
        for p in patterns:
            icon = {
                "peak_hours": "⏰",
                "preferred_tools": "🔧",
                "recurring_topics": "💡",
                "usage_frequency": "📊",
                "day_preferences": "📅",
            }.get(p.pattern_type, "📌")
            lines.append(f"  {icon} {p.description} (confidence: {p.confidence:.0%})")

        return "\n".join(lines)

    def get_tools_for_topic(
        self,
        text: str,
        *,
        top_n: int = 3,
        min_uses: int = 2,
        min_overlap: int = 1,
    ) -> list:
        """Tools historically used on tasks sharing topic words with ``text``.

        Looks back at recorded interactions, finds those whose ``topic_words``
        overlap by at least ``min_overlap`` with the words extracted from
        ``text``, and returns the top tools by frequency. Used by the agent
        to surface a "last time you asked about X you used tool Y" hint
        before the agent picks tools — directly attacks the failure mode
        where the agent forgets it has a browser.

        Returns: list of ``(tool_name, count)`` tuples, longest-first.
        """
        if not text:
            return []
        query_words = {
            w.lower() for w in text.split() if len(w) > 4 and w.isalpha()
        }
        if not query_words:
            return []
        tool_counts: Counter = Counter()
        for entry in self.data.get("interactions", []):
            entry_words = set(entry.get("topic_words") or [])
            if len(query_words & entry_words) < min_overlap:
                continue
            for t in entry.get("tools") or []:
                if t:
                    tool_counts[t] += 1
        return [(t, c) for t, c in tool_counts.most_common(top_n) if c >= min_uses]

    def get_personalization_prompt(self) -> str:
        """Generate personalization context for the system prompt."""
        patterns = self.detect_patterns()
        if not patterns:
            return ""

        parts = []
        for p in patterns:
            if p.confidence > 0.3:  # Only include confident patterns
                if p.pattern_type == "peak_hours":
                    parts.append(f"User is typically most active around {p.data.get('peak_hour', '?')}:00.")
                elif p.pattern_type == "preferred_tools":
                    top = [t for t, _ in p.data.get("top_tools", [])[:3]]
                    if top:
                        parts.append(f"User frequently uses: {', '.join(top)}.")
                elif p.pattern_type == "recurring_topics":
                    topics = [w for w, _ in p.data.get("topics", [])[:5]]
                    if topics:
                        parts.append(f"Recurring interests: {', '.join(topics)}.")

        return " ".join(parts)
