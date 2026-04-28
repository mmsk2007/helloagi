"""Task fingerprinting — stable hash of a task's identity.

Two tasks with the same fingerprint are treated as "the same task" for routing,
outcome aggregation, and skill crystallization. The hash is intentionally
forgiving (case, whitespace, trivial punctuation) so that paraphrases route
together, but strict enough that genuinely different tasks fall apart.

Fingerprints are stored on SkillContract and CouncilTrace so the router can
ask "have we seen this before, and how did it go?" in O(1).
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable, Optional


_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


def normalize_task_text(text: str) -> str:
    """Lowercase, strip trivial punctuation, collapse whitespace.

    Kept deliberately simple — heavier normalization (stemming, stopword
    removal) buys little for fingerprint stability and complicates audit.
    """
    if not text:
        return ""
    lowered = text.strip().lower()
    de_punct = _PUNCT_RE.sub(" ", lowered)
    return _WS_RE.sub(" ", de_punct).strip()


def task_fingerprint(
    text: str,
    *,
    task_type: str = "",
    tool_hints: Optional[Iterable[str]] = None,
) -> str:
    """Compute a 16-char fingerprint for a task.

    `task_type` and `tool_hints` are optional discriminators. When the router
    has no tool hints (Phase 1), the fingerprint is purely text-derived.
    """
    parts = [normalize_task_text(text)]
    if task_type:
        parts.append(f"::type={task_type.strip().lower()}")
    if tool_hints:
        # Sorted so order doesn't shift the fingerprint.
        sig = ",".join(sorted({t.strip().lower() for t in tool_hints if t}))
        if sig:
            parts.append(f"::tools={sig}")
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:16]


__all__ = ["task_fingerprint", "normalize_task_text"]
