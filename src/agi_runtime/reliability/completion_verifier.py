"""Completeness Verifier — blocks false completion claims.

Inspired by VLAA-GUI's stop verification: after the agent generates a
final response, this module checks whether the claimed actions were
actually performed.  Extends OutputGuard's phantom-action detection
with evidence-based verification.

When ``session_evidence`` is provided (tool rows with optional outputs),
claims are checked against **observable** tool kinds (file/shell/browser),
not merely whether any tool ran in the session.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Pattern, Sequence, Set

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

_FILE_TOOLS: Set[str] = {"file_write", "file_patch"}
_SHELL_TOOLS: Set[str] = {"bash_exec", "python_exec"}
_BROWSER_TOOLS: Set[str] = {
    "browser_navigate", "browser_read", "browser_screenshot",
}
_RESEARCH_TOOLS: Set[str] = {"web_search", "web_fetch", "session_search", "memory_recall"}
_NOTIFY_TOOLS: Set[str] = {"notify_user", "send_voice", "send_image", "send_file"}
_DELEGATION_TOOLS: Set[str] = {"delegate_task"}


def _norm_tool(name: str) -> str:
    return (name or "").strip().lower()


def _output_blob(row: Dict[str, Any]) -> str:
    parts: List[str] = []
    out = row.get("output")
    if isinstance(out, str) and out.strip():
        parts.append(out)
    inp = row.get("input")
    if isinstance(inp, dict):
        for key in ("command", "path", "url", "query", "q", "message"):
            v = inp.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(v)
    return "\n".join(parts).lower()


def _any_ok_tool(evidence: Sequence[Dict[str, Any]], names: Set[str]) -> bool:
    for row in evidence:
        if not row.get("ok", False):
            continue
        if _norm_tool(str(row.get("tool", ""))) in names:
            return True
    return False


def _bash_suggests_delete(blob: str) -> bool:
    if not blob:
        return False
    return bool(re.search(r"\b(rm|del|rmdir|remove-item|erase)\b", blob, re.IGNORECASE))


def _bash_suggests_install(blob: str) -> bool:
    if not blob:
        return False
    return bool(re.search(
        r"\b(pip install|npm install|apt install|brew install|choco install|conda install)\b",
        blob,
        re.IGNORECASE,
    ))


def _bash_suggests_deploy(blob: str) -> bool:
    if not blob:
        return False
    return bool(re.search(r"\b(git push|deploy|kubectl apply|docker push)\b", blob, re.IGNORECASE))


def _claim_supported_by_evidence(
    claim_label: str,
    evidence: Sequence[Dict[str, Any]],
) -> bool:
    """Return True if session tool rows plausibly support this completion claim."""
    if not evidence:
        return False

    if claim_label in ("file-created", "file-updated"):
        return _any_ok_tool(evidence, _FILE_TOOLS)

    if claim_label == "command-ran":
        return _any_ok_tool(evidence, _SHELL_TOOLS)

    if claim_label == "deleted":
        if _any_ok_tool(evidence, _FILE_TOOLS):
            for row in evidence:
                if not row.get("ok"):
                    continue
                if _norm_tool(str(row.get("tool", ""))) == "file_patch":
                    blob = _output_blob(row)
                    if "delet" in blob or "remov" in blob:
                        return True
                if _norm_tool(str(row.get("tool", ""))) == "bash_exec":
                    if _bash_suggests_delete(_output_blob(row)):
                        return True
        if _any_ok_tool(evidence, {"bash_exec"}):
            for row in evidence:
                if row.get("ok") and _norm_tool(str(row.get("tool", ""))) == "bash_exec":
                    if _bash_suggests_delete(_output_blob(row)):
                        return True
        return False

    if claim_label == "searched":
        if _any_ok_tool(evidence, _RESEARCH_TOOLS | _BROWSER_TOOLS):
            return True
        return False

    if claim_label == "deployed":
        if _any_ok_tool(evidence, _DELEGATION_TOOLS):
            return True
        if _any_ok_tool(evidence, _SHELL_TOOLS):
            for row in evidence:
                if row.get("ok") and _norm_tool(str(row.get("tool", ""))) in _SHELL_TOOLS:
                    if _bash_suggests_deploy(_output_blob(row)):
                        return True
        return False

    if claim_label == "installed":
        if _any_ok_tool(evidence, _SHELL_TOOLS):
            for row in evidence:
                if row.get("ok") and _norm_tool(str(row.get("tool", ""))) in _SHELL_TOOLS:
                    if _bash_suggests_install(_output_blob(row)):
                        return True
        return False

    if claim_label == "email-sent":
        return _any_ok_tool(evidence, _NOTIFY_TOOLS | _DELEGATION_TOOLS)

    return False


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
        session_evidence: Optional[List[Dict[str, Any]]] = None,
    ) -> CompletionCheck:
        """Check if response claims are backed by evidence.

        ``session_evidence`` rows should look like
        ``{"tool": str, "ok": bool, "output": str}`` (``output`` may be truncated).
        When this list is non-empty, file/shell/browser-style claims are matched
        against **tool kinds** in the evidence, not only ``tool_calls_made``.
        """
        if not response_text:
            return CompletionCheck(status="verified", reasons=["empty-response"])

        tools_used = tools_used or []
        claims_found = 0
        claims_verified = 0
        reasons: List[str] = []
        use_evidence = bool(session_evidence)

        for label, pattern, requires_tool in _CLAIM_PATTERNS:
            if not pattern.search(response_text):
                continue
            claims_found += 1
            if not requires_tool:
                if tool_calls_made > 0:
                    claims_verified += 1
                    reasons.append(f"verified:{label}")
                else:
                    reasons.append(f"unverified:{label}")
                continue

            if tool_calls_made == 0:
                reasons.append(f"phantom:{label}")
                continue

            if use_evidence:
                if session_evidence is not None and _claim_supported_by_evidence(label, session_evidence):
                    claims_verified += 1
                    reasons.append(f"verified:{label}")
                else:
                    reasons.append(f"insufficient-evidence:{label}")
            else:
                claims_verified += 1
                reasons.append(f"verified:{label}")

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

        insufficient = [r for r in reasons if r.startswith("insufficient-evidence:")]
        if insufficient and claims_verified == 0 and tool_calls_made > 0:
            return CompletionCheck(
                status="phantom",
                reasons=reasons,
                claims_found=claims_found,
                claims_verified=claims_verified,
                suggestion="Agent claims a specific outcome, but the tools run this session "
                           "do not support that claim (e.g. file work requires file_write/file_patch). "
                           "Run the correct tools and try again.",
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
