"""Inspirational quotes for HelloAGI — from Think and Grow Rich, The Secret, and the AGI revolution.

These quotes appear during onboarding, startup, and throughout the experience
to remind users they're part of something bigger.
"""

from __future__ import annotations

import random

# ── Think and Grow Rich — Napoleon Hill ──────────────────────────────────────

THINK_AND_GROW_RICH = [
    "Whatever the mind can conceive and believe, it can achieve.",
    "The starting point of all achievement is desire.",
    "Strength and growth come only through continuous effort and struggle.",
    "Don't wait. The time will never be just right.",
    "Set your mind on a definite goal and observe how quickly the world stands aside to let you pass.",
    "Every adversity, every failure, every heartache carries with it the seed of an equal or greater benefit.",
    "You are the master of your destiny. You can influence, direct and control your own environment.",
    "A goal is a dream with a deadline.",
    "When defeat comes, accept it as a signal that your plans are not sound, rebuild those plans, and set sail once more.",
    "Great achievement is usually born of great sacrifice, and is never the result of selfishness.",
    "The way of success is the way of continuous pursuit of knowledge.",
    "Action is the real measure of intelligence.",
    "If you do not conquer self, you will be conquered by self.",
    "Patience, persistence and perspiration make an unbeatable combination for success.",
    "Think twice before you speak, because your words and influence will plant the seed of either success or failure.",
]

# ── The Secret — Rhonda Byrne ────────────────────────────────────────────────

THE_SECRET = [
    "You become what you think about most. But you also attract what you think about most.",
    "Your power is in your thoughts, so stay awake. In other words, remember to remember.",
    "There is no such thing as a hopeless situation. Every single circumstance of your life can change.",
    "See the things that you want as already yours.",
    "The universe is change; our life is what our thoughts make it.",
    "You are the creator of your own reality.",
    "Everything is possible. Nothing is impossible.",
    "What you think, you create. What you feel, you attract. What you imagine, you become.",
    "Your thoughts become things.",
    "The only reason any person does not have enough money is because they are blocking money from coming to them with their thoughts.",
    "You create your own universe as you go along.",
    "Your life is in your hands. No matter where you are now, no matter what has happened in your life, you can begin to consciously choose your thoughts.",
    "When you visualize, then you materialize.",
    "Decide what you want. Believe you can have it. Believe you deserve it.",
    "Life is meant to be abundant in ALL areas.",
]

# ── The AGI Revolution ───────────────────────────────────────────────────────

AGI_REVOLUTION = [
    "You are not just building software. You are shaping the future of intelligence.",
    "The age of AGI is not coming — it's here. And you are at the frontier.",
    "A new revolution begins. Not of machines replacing humans, but of humans empowered by intelligence.",
    "HelloAGI: Where governed autonomy meets unlimited potential.",
    "Every great revolution started with a single spark. This is yours.",
    "The world is about to change. And you are holding the tool that changes it.",
    "Intelligence, governed by principles. Autonomy, guided by purpose. This is the way.",
    "We don't just build agents. We birth digital minds that grow, learn, and evolve.",
    "The first AGI revolution is local-first, safety-first, and human-first.",
    "Your agent isn't a chatbot. It's a growing intelligence with its own identity.",
    "From this moment, every interaction makes your agent smarter. Welcome to the evolution.",
    "What if your AI didn't just answer questions — but actually did the work?",
    "HelloAGI: The bridge between human ambition and autonomous execution.",
    "This is not science fiction. This is your terminal. And your agent is ready.",
    "The future of AI is not locked in the cloud. It's running on your machine, governed by your rules.",
]

# ── All quotes combined ─────────────────────────────────────────────────────

ALL_QUOTES = THINK_AND_GROW_RICH + THE_SECRET + AGI_REVOLUTION

_SOURCES = {
    "think_and_grow_rich": THINK_AND_GROW_RICH,
    "the_secret": THE_SECRET,
    "agi_revolution": AGI_REVOLUTION,
}


def get_random_quote(source: str = None) -> tuple:
    """Get a random quote. Returns (quote, source_name)."""
    if source and source in _SOURCES:
        pool = _SOURCES[source]
        src_name = source.replace("_", " ").title()
    else:
        # Random from all
        choice = random.choice(list(_SOURCES.keys()))
        pool = _SOURCES[choice]
        src_name = choice.replace("_", " ").title()

    quote = random.choice(pool)
    return quote, src_name


def get_startup_quote() -> str:
    """Get a formatted quote for startup/banner."""
    quote, source = get_random_quote()
    return f'"{quote}"\n  — {source}'


def get_onboarding_quotes() -> list:
    """Get a sequence of quotes for onboarding steps."""
    return [
        random.choice(THINK_AND_GROW_RICH),
        random.choice(THE_SECRET),
        random.choice(AGI_REVOLUTION),
    ]
