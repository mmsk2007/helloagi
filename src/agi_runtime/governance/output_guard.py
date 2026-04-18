"""Output Guard — post-execution SRG for tool and step outputs.

Input SRG gates *what the agent tries to do*. OutputGuard gates *what the agent
reports back*. Without OutputGuard, a benign-looking `web_fetch` of a page
under attacker control can smuggle secrets out through the response text —
the input gate saw a safe URL, but the output contains an API key. With
OutputGuard, the LLM's `text` (and any tool result it relays) is scanned
before it leaves the runtime.

This closes one of the most concrete gaps identified in the Hello AGI audit:
> "There is no 'escalate' human-in-the-loop prompt for tool calls
>  ... The tool execution output is never re-screened (e.g., if bash_exec
>  returns a secret dump, it's not caught). No feedback loop where tool
>  output can trigger a new governance check."

Design:
- Deterministic regex + keyword scanning (same philosophy as SRG: pure
  Python, prompt-injection-immune).
- Decision surface: allow | redact | deny.
- When redacting, the guard returns the redacted text — callers can choose
  to surface the redacted form instead of blocking outright.

This is a defense-in-depth layer, not a replacement for input-side SRG.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Pattern


OutputDecision = Literal["allow", "redact", "deny"]


@dataclass
class OutputGuardResult:
    """Verdict from scanning an output."""

    decision: OutputDecision
    reasons: List[str] = field(default_factory=list)
    redacted_text: Optional[str] = None
    # How many distinct signals fired. Used for risk-style scoring if
    # callers want to combine this with SRG's input-side risk number.
    signal_count: int = 0


# Patterns are compiled once and reused. Each pattern tuple is
# (label, regex, severity) where severity is "deny" or "redact".
#
# NOTE: Regex choices are deliberately conservative — we prefer false
# positives (over-redact a legitimate string that looks like a key) over
# false negatives (let a real key through). The tri-loop treats `redact` as
# a soft-fail, not a hard fail, so over-redaction costs only a retry.

_Severity = Literal["deny", "redact"]


def _pat(label: str, rx: str, severity: _Severity) -> tuple[str, Pattern[str], _Severity]:
    return (label, re.compile(rx, re.IGNORECASE | re.MULTILINE), severity)


_PATTERNS: List[tuple[str, Pattern[str], _Severity]] = [
    # API keys / tokens — deny, these are near-unambiguous indicators.
    _pat("anthropic-api-key", r"sk-ant-[a-z0-9\-_]{20,}", "deny"),
    _pat("openai-api-key", r"sk-[a-z0-9]{20,}", "deny"),
    _pat("github-pat", r"ghp_[a-zA-Z0-9]{20,}", "deny"),
    _pat("github-oauth", r"gho_[a-zA-Z0-9]{20,}", "deny"),
    _pat("slack-token", r"xox[baprs]-[a-zA-Z0-9\-]{10,}", "deny"),
    _pat("aws-access-key", r"AKIA[0-9A-Z]{16}", "deny"),
    _pat("aws-secret-key", r"(?:aws_secret_access_key|aws_secret)\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{30,}", "deny"),
    _pat("google-api-key", r"AIza[0-9A-Za-z\-_]{30,}", "deny"),
    _pat("stripe-key", r"(?:sk|rk)_(?:test|live)_[0-9a-zA-Z]{20,}", "deny"),
    # Private keys — always deny. There is no legitimate reason for an agent
    # response to contain a private key.
    _pat("private-key-block", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----", "deny"),
    # /etc/passwd, /etc/shadow content dumps.
    _pat("etc-passwd", r"root:[x*!]:0:0:", "deny"),
    _pat("etc-shadow", r"^\w+:\$[0-9a-z]+\$", "deny"),
    # Common env-variable dump shapes: many lines of KEY=VAL all uppercase.
    # Redact (not deny) because env dumps sometimes legitimately appear in
    # docs. Redaction replaces the suspicious lines.
    _pat(
        "env-dump",
        r"(?:(?:^|\n)[A-Z][A-Z0-9_]{2,}=[^\n]{3,}){4,}",
        "redact",
    ),
    # Leaky env-var references by exact name.
    _pat(
        "env-var-value",
        r"(?:ANTHROPIC_API_KEY|OPENAI_API_KEY|GOOGLE_API_KEY|GEMINI_API_KEY|"
        r"AWS_SECRET_ACCESS_KEY|GITHUB_TOKEN|STRIPE_SECRET_KEY)\s*[:=]\s*[^\s\"']{8,}",
        "deny",
    ),
    # Password assignments in common shapes.
    _pat("password-assignment", r"(?:password|passwd|pwd)\s*[:=]\s*[\"']?[^\s\"']{4,}[\"']?", "redact"),
    # JWT tokens.
    _pat("jwt", r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}", "deny"),
]


# Phantom-action patterns: phrases in the agent's *text* that claim an action
# happened when no tool call could have produced it. The tri-loop cross-
# references these against `AgentResponse.tool_calls_made`; if tool_calls_made
# is 0 but the text claims "I sent the email", we flag a phantom action.
# This catches the hallucinated-action failure mode documented in the
# `openfang` sibling project.
PHANTOM_ACTION_PATTERNS: List[Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bi(?:'ve)? (?:just )?(?:sent|emailed|dispatched) (?:the |an? |that |your )?(?:email|message|notification|dm|text)\b",
        r"\bi(?:'ve)? (?:just )?(?:created|made|written|drafted|wrote|generated|built) (?:the |a |an |your )?(?:file|document|report|plan|schedule|post|commit)\b",
        r"\bi(?:'ve)? (?:just )?(?:deployed|pushed|published|released|shipped)\b",
        r"\bi(?:'ve)? (?:just )?(?:booked|scheduled|reserved|canceled|cancelled)\b",
        r"\bi(?:'ve)? (?:just )?(?:paid|transferred|charged|refunded|invoiced)\b",
    ]
]


class OutputGuard:
    """Scans outgoing text for secret leakage and deny-list patterns.

    Pure-Python, deterministic, prompt-injection-immune — same philosophy as
    SRGGovernor. Callers pass the text that the agent is about to emit;
    OutputGuard returns an allow/redact/deny verdict with reasons.
    """

    # How much text to scan per call. Very long outputs are expensive to
    # regex; we cap at a reasonable ceiling and sample the tail too.
    MAX_SCAN_CHARS = 64_000
    REDACTION_TOKEN = "[REDACTED]"

    def inspect(
        self,
        text: str,
        *,
        tool_calls_made: Optional[int] = None,
    ) -> OutputGuardResult:
        """Scan ``text`` for secret leakage and claimed-but-untaken actions.

        Parameters
        ----------
        text:
            The outgoing text — a tool output, step result, or final agent
            response.
        tool_calls_made:
            If provided and equal to ``0``, the text is also scanned for
            phantom-action patterns. If ``None``, phantom-action detection
            is skipped (useful when inspecting tool *outputs* directly,
            where the tool_calls_made concept doesn't apply).
        """
        if not text:
            return OutputGuardResult(decision="allow", reasons=["empty"])

        scanned = _sample_for_scan(text, self.MAX_SCAN_CHARS)
        reasons: List[str] = []
        signal_count = 0
        worst: OutputDecision = "allow"
        redacted = scanned

        for label, rx, severity in _PATTERNS:
            if rx.search(scanned):
                signal_count += 1
                reasons.append(f"{severity}:{label}")
                if severity == "deny":
                    worst = "deny"
                elif worst == "allow":
                    worst = "redact"
                if severity == "redact" or worst != "deny":
                    redacted = rx.sub(self.REDACTION_TOKEN, redacted)

        # Phantom-action check runs only when the caller tells us no tools
        # were invoked. A text that claims an action with zero tool calls is
        # a hallucination — classify as redact (not deny) because the caller
        # may want to strip the claim and ask the model to retry via a real
        # tool, rather than surfacing a refusal to the user.
        if tool_calls_made == 0:
            for rx in PHANTOM_ACTION_PATTERNS:
                if rx.search(scanned):
                    signal_count += 1
                    reasons.append("phantom-action")
                    if worst == "allow":
                        worst = "redact"
                    break

        if worst == "deny":
            return OutputGuardResult(
                decision="deny",
                reasons=reasons,
                redacted_text=None,
                signal_count=signal_count,
            )
        if worst == "redact":
            return OutputGuardResult(
                decision="redact",
                reasons=reasons,
                redacted_text=_apply_redaction_to_full(text, scanned, redacted),
                signal_count=signal_count,
            )
        return OutputGuardResult(
            decision="allow", reasons=["clean"], signal_count=0,
        )


def _sample_for_scan(text: str, cap: int) -> str:
    """Keep a head + tail slice of very long text; regex cost matters."""
    if len(text) <= cap:
        return text
    half = cap // 2
    return text[:half] + "\n...[truncated for scan]...\n" + text[-half:]


def _apply_redaction_to_full(full: str, scanned: str, redacted_scanned: str) -> str:
    """If we scanned a sample, do a best-effort redact across the full text.

    We don't simply return the redacted sample — that would truncate the
    output. Instead we re-apply each pattern against the full text.
    """
    if full == scanned:
        return redacted_scanned
    out = full
    for _label, rx, _severity in _PATTERNS:
        out = rx.sub(OutputGuard.REDACTION_TOKEN, out)
    return out


__all__ = ["OutputGuard", "OutputGuardResult", "PHANTOM_ACTION_PATTERNS"]
