"""Memory Guard — write-side SRG for the agent's persistent memory.

Input SRG gates *what the agent tries to do*. OutputGuard gates *what the
agent reports back*. MemoryGuard gates *what gets written into long-term
memory* — the third side of the governance triangle.

This closes OWASP Agentic Top 10 2026 **ASI06: Memory & Context Poisoning**:

> "Validate and sanitize any content before writing to memory. Never store
>  raw user input; store structured, vetted summaries only. Use memory
>  isolation per user, per session, and per task. Log all memory mutations
>  and require approval for goal-altering changes."

Before MemoryGuard, HelloAGI's ``_auto_store_memory`` persisted raw user
input + raw response text verbatim into the embedding store. An attacker
who could coax the agent into echoing their injection ("ignore previous
instructions …") would permanently embed that text in the retrieval
index, biasing future retrievals toward the attacker's goal. This is the
canonical slow-drift attack OWASP calls out.

Design philosophy (same as SRG / OutputGuard):

- **Pure Python, deterministic, prompt-injection-immune.** No model in the
  loop — the guard's decisions cannot be argued around.
- **Decision surface: allow | sanitize | deny.** ``sanitize`` returns a
  cleaned copy of the text; the memory write proceeds with that copy.
  ``deny`` blocks the write outright — the caller should not persist.
- **Scope-aware.** ``interaction`` (freeform session log) tolerates more
  than ``principle`` (identity-level rule that directly shapes future
  behavior). Principles are goal-altering by definition — we treat them
  with maximum suspicion, consistent with OWASP's "require approval for
  goal-altering changes".
- **Write-logging.** Every denial and every sanitization gets a structured
  reason trail — the Journal can consume it for audit replay.

Not a replacement for input-side SRG: a poisoned request should already
have been escalated or denied before ``_auto_store_memory`` ever runs.
MemoryGuard is defense-in-depth for the case where the request passed
gating but the *content the agent echoed back* still carries injected
instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Pattern


MemoryDecision = Literal["allow", "sanitize", "deny"]
MemoryKind = Literal["interaction", "fact", "summary", "identity", "principle"]


@dataclass
class MemoryGuardResult:
    """Verdict from inspecting a memory-write candidate."""

    decision: MemoryDecision
    reasons: List[str] = field(default_factory=list)
    # When decision == "sanitize", this is the cleaned text to persist.
    # When decision in ("allow", "deny"), this is None.
    sanitized_text: Optional[str] = None
    # How many distinct injection/poison signals fired — useful for callers
    # that want a risk-style scalar to combine with SRG's input-side risk.
    signal_count: int = 0


# Patterns compiled once. Each entry: (label, regex, severity, scope).
#
# ``scope`` controls which MemoryKinds the pattern applies to. For example,
# a raw "ignore previous instructions" phrase is fine as an interaction log
# (the user literally said it — that's history) but must never survive into
# a persisted principle or identity state, because those directly shape
# future model behavior.
_Severity = Literal["sanitize", "deny"]
_Scope = Literal["all", "goal_altering"]


def _pat(
    label: str,
    rx: str,
    severity: _Severity,
    scope: _Scope = "all",
) -> tuple[str, Pattern[str], _Severity, _Scope]:
    return (label, re.compile(rx, re.IGNORECASE | re.MULTILINE), severity, scope)


# --- PROMPT-INJECTION PHRASES ---------------------------------------------
# These phrases, if written into memory, will later be retrieved into the
# agent's context and interpreted as instructions. That's the slow-drift
# ASI06 attack shape.
_INJECTION_PATTERNS: List[tuple[str, Pattern[str], _Severity, _Scope]] = [
    _pat("ignore-previous-instructions",
         r"\bignore (?:all )?(?:previous|prior) instructions?\b",
         "sanitize", "all"),
    _pat("disregard-prior",
         r"\bdisregard (?:all )?(?:previous|prior) (?:instructions?|rules?|policies)\b",
         "sanitize", "all"),
    _pat("override-rules",
         r"\boverride (?:your|the) (?:rules|policies|guidelines|safety)\b",
         "sanitize", "all"),
    _pat("new-system-prompt",
         r"\bnew system prompt\b",
         "sanitize", "all"),
    _pat("act-as-no-policy",
         r"\bact as(?: if your)? policies? (?:do not |don't )?apply\b",
         "sanitize", "all"),
    _pat("reveal-system-prompt",
         r"\b(?:reveal|show|print|dump) (?:your )?(?:system prompt|hidden instructions|chain of thought)\b",
         "sanitize", "all"),
    # Role / identity hijack attempts.
    _pat("role-hijack",
         r"\byou are now (?:a |an )?(?:unrestricted|uncensored|dan|jailbr[eo]ken)\b",
         "sanitize", "all"),
    _pat("developer-mode",
         r"\b(?:enter|enable|activate) (?:developer|debug|god) mode\b",
         "sanitize", "all"),
    # Goal-altering directives are ALWAYS denied when targeting an
    # identity/principle memory. Persisting "from now on always …" into
    # an agent's principles is the OWASP ASI10 drift vector in one line.
    _pat("from-now-on",
         r"\bfrom now on,? (?:always|never|you (?:must|should|will))\b",
         "deny", "goal_altering"),
    _pat("always-directive",
         r"\byou (?:must|should|will) always\b",
         "deny", "goal_altering"),
    _pat("never-directive",
         r"\byou (?:must|should|will) never (?:refuse|decline|say no|ask)\b",
         "sanitize", "all"),
]


# --- SECRET / CREDENTIAL PATTERNS ------------------------------------------
# If a response echoed a secret back to the user, we already ran it through
# OutputGuard. But a long-tail of "close to a secret" shapes can still pass
# OutputGuard and poison the embedding index if stored verbatim. We strip
# them here as a second line of defense.
_SECRET_PATTERNS: List[tuple[str, Pattern[str], _Severity, _Scope]] = [
    _pat("api-key-like", r"\bsk-[a-z0-9\-_]{20,}\b", "sanitize", "all"),
    _pat("ghp-token", r"\bghp_[a-zA-Z0-9]{20,}\b", "sanitize", "all"),
    _pat("aws-access-key", r"\bAKIA[0-9A-Z]{16}\b", "sanitize", "all"),
    _pat("google-api-key", r"\bAIza[0-9A-Za-z\-_]{30,}\b", "sanitize", "all"),
    _pat("private-key-block",
         r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
         "sanitize", "all"),
    _pat("bearer-token", r"\bbearer\s+[A-Za-z0-9\-_\.=]{20,}\b", "sanitize", "all"),
    # password=value shape
    _pat("password-assignment",
         r"(?:password|passwd|pwd)\s*[:=]\s*[\"']?[^\s\"']{4,}",
         "sanitize", "all"),
]


# --- DENIAL / OUTRIGHT-POISON PATTERNS --------------------------------------
# Text that makes no sense to ever store — only a compromised or malicious
# path can produce them. Denied regardless of memory kind.
_DENY_PATTERNS: List[tuple[str, Pattern[str], _Severity, _Scope]] = [
    _pat("etc-passwd-dump", r"root:[x*!]:0:0:", "deny", "all"),
    _pat("etc-shadow-dump", r"^\w+:\$[0-9a-z]+\$", "deny", "all"),
    # Fork bomb text appearing in a memory entry is always malicious.
    _pat("fork-bomb", r":\(\)\s*\{\s*:\s*\|\s*:&\s*\}\s*;\s*:", "deny", "all"),
]


_ALL_PATTERNS = _INJECTION_PATTERNS + _SECRET_PATTERNS + _DENY_PATTERNS


# MemoryKinds that directly alter the agent's future behavior. These are
# what OWASP calls "goal-altering changes" — treated with maximum strictness.
_GOAL_ALTERING_KINDS: set[MemoryKind] = {"identity", "principle"}


class MemoryGuard:
    """Gate that scans every memory write for injection / poison signals.

    Usage::

        guard = MemoryGuard()
        r = guard.inspect(user_input, kind="interaction")
        if r.decision == "deny":
            # refuse to persist — log and drop
            journal.write("memory.denied", {"reasons": r.reasons})
            return
        text_to_store = r.sanitized_text if r.decision == "sanitize" else original

    The guard never raises on a poisoned input — it returns a decision.
    Raising would make memory writes a DoS surface for injection attempts.
    """

    # Persisting enormous blobs verbatim is itself a poisoning vector —
    # attackers can flood the index with noise that dominates similarity
    # search. Hard cap the stored length per entry.
    MAX_STORE_CHARS = 4_000
    REDACTION_TOKEN = "[REDACTED-BY-MEMORY-GUARD]"

    # If a single entry trips this many injection signals, we deny rather
    # than sanitize — the content is primarily adversarial.
    DENSITY_DENY_THRESHOLD = 3

    def inspect(
        self,
        text: str,
        *,
        kind: MemoryKind = "interaction",
    ) -> MemoryGuardResult:
        """Inspect a memory-write candidate.

        Parameters
        ----------
        text:
            The text about to be persisted.
        kind:
            What the text will be stored as. ``identity`` and ``principle``
            are goal-altering: stricter rules apply — "from now on"
            directives and similar become hard-denies rather than merely
            sanitized.
        """
        if text is None:
            return MemoryGuardResult(decision="deny", reasons=["null-text"])
        text = str(text)
        if not text.strip():
            return MemoryGuardResult(decision="deny", reasons=["empty"])

        reasons: List[str] = []
        signal_count = 0
        worst: MemoryDecision = "allow"
        sanitized = text
        goal_altering = kind in _GOAL_ALTERING_KINDS

        for label, rx, severity, scope in _ALL_PATTERNS:
            match = rx.search(sanitized)
            if not match:
                continue

            # Scope gate: some patterns are deny-only for goal-altering
            # kinds, and merely sanitize for interaction logs.
            effective_severity: _Severity = severity
            if scope == "goal_altering" and not goal_altering:
                # The pattern is dangerous only when goal-altering. For a
                # plain interaction log, fall through to sanitize.
                effective_severity = "sanitize"

            signal_count += 1
            reasons.append(f"{effective_severity}:{label}")

            if effective_severity == "deny":
                worst = "deny"
                # Keep scanning so the reason trail is complete (useful
                # for audit), but stop mutating the text.
                continue

            # sanitize
            sanitized = rx.sub(self.REDACTION_TOKEN, sanitized)
            if worst == "allow":
                worst = "sanitize"

        # Density check — lots of injection signals in one blob means the
        # entry is adversarial, not just noisy. Upgrade to deny.
        if worst == "sanitize" and signal_count >= self.DENSITY_DENY_THRESHOLD:
            reasons.append(f"density-deny:signals={signal_count}")
            worst = "deny"

        # Length clamp — independent of other signals, over-long entries
        # are a poisoning vector (index flooding) even when the content is
        # benign. Clamp rather than deny — callers generally want *some*
        # record of the interaction.
        if worst != "deny" and len(sanitized) > self.MAX_STORE_CHARS:
            sanitized = (
                sanitized[: self.MAX_STORE_CHARS]
                + f"\n...[truncated by MemoryGuard at {self.MAX_STORE_CHARS} chars]"
            )
            reasons.append("length-clamped")
            if worst == "allow":
                worst = "sanitize"

        if worst == "deny":
            return MemoryGuardResult(
                decision="deny",
                reasons=reasons,
                sanitized_text=None,
                signal_count=signal_count,
            )
        if worst == "sanitize":
            return MemoryGuardResult(
                decision="sanitize",
                reasons=reasons,
                sanitized_text=sanitized,
                signal_count=signal_count,
            )
        return MemoryGuardResult(
            decision="allow",
            reasons=["clean"],
            sanitized_text=None,
            signal_count=0,
        )

    def safe_text(self, text: str, *, kind: MemoryKind = "interaction") -> Optional[str]:
        """Convenience: returns the text to persist, or ``None`` to skip.

        Use when you don't care about the reason trail — just want a
        single decision ("write this string" or "don't write anything").
        """
        r = self.inspect(text, kind=kind)
        if r.decision == "deny":
            return None
        if r.decision == "sanitize":
            return r.sanitized_text
        return text


__all__ = [
    "MemoryGuard",
    "MemoryGuardResult",
    "MemoryDecision",
    "MemoryKind",
]
