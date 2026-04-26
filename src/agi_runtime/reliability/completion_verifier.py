"""Completeness Verifier — blocks false completion claims.

Inspired by VLAA-GUI's stop verification: after the agent generates a
final response, this module checks whether the claimed actions were
actually performed.  Extends OutputGuard's phantom-action detection
with evidence-based verification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Pattern

VerificationStatus = Literal["verified", "unverified", "phantom"]


@dataclass
class CompletionCheck:
    """Result of checking a completion claim."""
    status: VerificationStatus
    reasons: List[str] = field(default_factory=list)
    claims_found: int = 0
    claims_verified: int = 0
    suggestion: str = ""


# Patterns that indicate the agent is claiming an action was completed.
# Each tuple: (label, regex, requires_tool_call)
_CLAIM_PATTERNS: List[tuple[str, Pattern[str], bool]] = [
    ("file-created", re.compile(
        r"(?:i(?:'ve)?|i've) (?:just )?(?:created|generated|written|saved|made) "
        r"(?:the |a |an |your )?(?:file|document|script|config)",
        re.IGNORECASE,
    ), True),
    ("file-updated", re.compile(
        r"(?:i(?:'ve)?|i've) (?:just )?(?:updated|modified|edited|patched|changed) "
        r"(?:the |a |an |your )?(?:file|document|code|script)",
        re.IGNORECASE,
    ), True),
    ("command-ran", re.compile(
        r"(?:i(?:'ve)?|i've) (?:just )?(?:run|ran|executed|performed) "
        r"(?:the |a |an |your )?(?:command|script|code|test|build)",
        re.IGNORECASE,
    ), True),
    ("email-sent", re.compile(
        r"(?:i(?:'ve)?|i've) (?:just )?(?:sent|emailed|dispatched) "
        r"(?:the |a |an |your )?(?:email|message|notification)",
        re.IGNORECASE,
    ), True),
    ("deployed", re.compile(
        r"(?:i(?:'ve)?|i've) (?:just )?(?:deployed|pushed|published|released|shipped)",
        re.IGNORECASE,
    ), True),
    ("installed", re.compile(
        r"(?:i(?:'ve)?|i've) (?:just )?(?:installed|set up|configured|initialized)",
        re.IGNORECASE,
    ), True),
    ("deleted", re.compile(
        r"(?:i(?:'ve)?|i've) (?:just )?(?:deleted|removed|cleaned up|purged)",
        re.IGNORECASE,
    ), True),
    ("searched", re.compile(
        r"(?:i(?:'ve)?|i've) (?:just )?(?:searched|looked up|found|researched|fetched)",
        re.IGNORECASE,
    ), True),
    ("task-complete", re.compile(
        r"(?:task|request|job|work) (?:is |has been )?(?:complete|done|finished|accomplished)",
        re.IGNORECASE,
    ), False),  # This one doesn't require a tool call itself
]


class CompletionVerifier:
    """Verifies that agent completion claims are backed by evidence.

    Usage::

        verifier = CompletionVerifier()
        check = verifier.verify(
            response_text="I've created the config file.",
            tool_calls_made=1,
            tools_used=["file_write"],
        )
        if check.status == "phantom":
            # Block or retry
    """

    def verify(
        self,
        response_text: str,
        tool_calls_made: int = 0,
        tools_used: Optional[List[str]] = None,
        tool_outputs: Optional[List[str]] = None,
    ) -> CompletionCheck:
        """Check if response claims are backed by evidence."""
        if not response_text:
            return CompletionCheck(status="verified", reasons=["empty-response"])

        tools_used = tools_used or []
        tool_outputs = tool_outputs or []
        claims_found = 0
        claims_verified = 0
        reasons: List[str] = []

        for label, pattern, requires_tool in _CLAIM_PATTERNS:
            if pattern.search(response_text):
                claims_found += 1
                if requires_tool and tool_calls_made == 0:
                    reasons.append(f"phantom:{label}")
                elif requires_tool and tool_calls_made > 0:
                    claims_verified += 1
                    reasons.append(f"verified:{label}")
                elif not requires_tool:
                    # "task complete" type claims — check if ANY tools were used
                    if tool_calls_made > 0:
                        claims_verified += 1
                        reasons.append(f"verified:{label}")
                    else:
                        reasons.append(f"unverified:{label}")

        if claims_found == 0:
            return CompletionCheck(
                status="verified",
                reasons=["no-completion-claims"],
                claims_found=0,
                claims_verified=0,
            )

        phantom_count = len([r for r in reasons if r.startswith("phantom:")])
        if phantom_count > 0 and tool_calls_made == 0:
            return CompletionCheck(
                status="phantom",
                reasons=reasons,
                claims_found=claims_found,
                claims_verified=claims_verified,
                suggestion="Agent claims actions but made no tool calls. "
                           "Please use the appropriate tools to perform the action.",
            )

        unverified_count = len([r for r in reasons if r.startswith("unverified:")])
        if unverified_count > 0 and claims_verified == 0:
            return CompletionCheck(
                status="unverified",
                reasons=reasons,
                claims_found=claims_found,
                claims_verified=claims_verified,
                suggestion="Agent claims completion but evidence is insufficient.",
            )

        return CompletionCheck(
            status="verified",
            reasons=reasons,
            claims_found=claims_found,
            claims_verified=claims_verified,
        )


__all__ = ["CompletionVerifier", "CompletionCheck", "VerificationStatus"]
