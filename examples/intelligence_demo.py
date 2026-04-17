"""Intelligence Demo — Sentiment, Patterns, and Context Compilation.

Shows HelloAGI's LifeMaster-inspired intelligence features:
- Mood/sentiment detection and tracking
- Behavioral pattern detection
- Unified context compilation
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agi_runtime.intelligence.sentiment import SentimentTracker
from agi_runtime.intelligence.patterns import PatternDetector
from agi_runtime.intelligence.context_compiler import ContextCompiler

# === Sentiment Detection ===
print("=== Mood & Sentiment Detection ===\n")

tracker = SentimentTracker(path="memory/demo_mood.json")

messages = [
    "This is awesome! I love how fast it works!",
    "I'm so frustrated, nothing is working properly",
    "Can you help me find the configuration file?",
    "I'm stuck on this bug and it's driving me crazy",
    "Finally got it working, I'm so happy!",
    "The results are amazing, thank you so much!",
]

for msg in messages:
    reading = tracker.detect(msg)
    icon = {"positive": "😊", "negative": "😔", "neutral": "😐"}[reading.sentiment]
    print(f"{icon} [{reading.sentiment:8s}] score={reading.score:+.2f} | \"{msg[:50]}...\"")

print(f"\nCurrent mood: {tracker.get_current_mood()}")
print(f"Mood trend: {tracker.get_mood_trend()}")
guidance = tracker.get_mood_guidance()
if guidance:
    print(f"Guidance: {guidance[:80]}...")

# === Pattern Detection ===
print("\n\n=== Behavioral Pattern Detection ===\n")

detector = PatternDetector(path="memory/demo_patterns.json")

# Simulate some interactions
interactions = [
    ("Write a Python script to scrape data", ["bash_exec", "file_write", "python_exec"]),
    ("Search the web for AI news", ["web_search", "web_fetch"]),
    ("Read the config file and update it", ["file_read", "file_write"]),
    ("Run the tests and fix any failures", ["bash_exec", "file_read", "file_patch"]),
    ("Deploy the application to production", ["bash_exec", "file_read"]),
    ("Write a function to parse JSON", ["python_exec", "file_write"]),
    ("Search for documentation on async Python", ["web_search", "web_fetch"]),
]

for text, tools in interactions:
    detector.record_interaction(text, tools)

insights = detector.get_insights()
print(insights)

# === Context Compilation ===
print("\n\n=== Compiled Context ===\n")

compiler = ContextCompiler()
ctx = compiler.compile(
    sentiment=tracker,
    session_messages=len(messages),
)

print(ctx.to_prompt())

# Cleanup demo files
import os
for f in ["memory/demo_mood.json", "memory/demo_patterns.json"]:
    if os.path.exists(f):
        os.remove(f)
