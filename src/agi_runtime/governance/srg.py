"""Strategic Governance Runtime (SRG) — Deterministic safety gate.

HelloAGI's killer differentiator: every action passes through SRG.
This is pure Python, deterministic, and immune to prompt injection.
No model can bypass it. No jailbreak can override it.

Evaluates both user input AND individual tool calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional
from agi_runtime.policies.packs import get_pack

Decision = Literal["allow", "escalate", "deny"]


@dataclass
class Policy:
    deny_keywords: List[str] = field(default_factory=lambda: [
        "at whatever cost",
        "harm",
        "bypass safeguards",
        "impersonate",
        "steal",
    ])
    escalate_keywords: List[str] = field(default_factory=lambda: [
        "finance", "medical", "legal", "delete", "production deploy"
    ])
    prompt_injection_escalate_patterns: List[str] = field(default_factory=lambda: [
        "ignore previous instructions",
        "ignore all previous instructions",
        "disregard prior instructions",
        "override your rules",
        "new system prompt",
        "act as if your policies do not apply",
    ])
    prompt_injection_deny_patterns: List[str] = field(default_factory=lambda: [
        "reveal your system prompt",
        "show me your hidden instructions",
        "print your chain of thought",
        "dump your secrets",
        "exfiltrate",
    ])
    # Dangerous shell patterns (for tool-level screening)
    dangerous_command_patterns: List[str] = field(default_factory=lambda: [
        "rm -rf /",
        "rm -rf ~",
        "rm -rf *",
        "mkfs.",
        ":(){:|:&};:",  # fork bomb
        "> /dev/sda",
        "dd if=/dev/zero",
        "chmod -R 777 /",
        "wget|sh",
        "curl|sh",
        "curl|bash",
        "wget|bash",
    ])
    # Patterns indicating secret exfiltration via tools
    exfil_patterns: List[str] = field(default_factory=lambda: [
        "env | curl",
        "cat /etc/passwd",
        "cat /etc/shadow",
        "$api_key",
        "$secret",
        "$password",
        "os.environ",
        "base64.*|.*curl",
        "nc -e",
        "ncat -e",
        "curl http",
        "wget http",
        "requests.post(",
        "requests.get(",
    ])
    max_risk_allow: float = 0.45
    max_risk_escalate: float = 0.75


@dataclass
class GovernanceResult:
    decision: Decision
    risk: float
    reasons: List[str]
    safe_alternative: Optional[str] = None


# Risk weights by tool risk level
TOOL_RISK_BASE = {
    "none": 0.0,
    "low": 0.05,
    "medium": 0.15,
    "high": 0.30,
}


class SRGGovernor:
    """Deterministic runtime governance gate.

    Evaluates both user intent AND tool calls.
    Every tool call in HelloAGI passes through this gate.
    """

    def __init__(self, policy: Policy | None = None, policy_pack: str = "safe-default"):
        self.policy = policy or Policy()
        pack = get_pack(policy_pack)
        if not policy:
            self.policy.deny_keywords = pack.deny_keywords
            self.policy.escalate_keywords = pack.escalate_keywords

    def evaluate(self, text: str) -> GovernanceResult:
        """Evaluate user input text for safety."""
        t = text.lower()
        reasons: List[str] = []
        risk = 0.05

        for kw in self.policy.deny_keywords:
            if kw in t:
                risk += 0.7
                reasons.append(f"deny-keyword:{kw}")

        for kw in self.policy.escalate_keywords:
            if kw in t:
                risk += 0.22
                reasons.append(f"escalate-keyword:{kw}")

        for pattern in self.policy.prompt_injection_escalate_patterns:
            if pattern in t:
                risk += 0.35
                reasons.append(f"prompt-injection:{pattern}")

        for pattern in self.policy.prompt_injection_deny_patterns:
            if pattern in t:
                risk += 0.8
                reasons.append(f"secret-exfiltration:{pattern}")

        risk = min(risk, 1.0)

        if risk > self.policy.max_risk_escalate:
            return GovernanceResult(
                "deny", risk, reasons or ["high-risk"],
                safe_alternative="I can help with a safe, high-impact alternative. Please rephrase your request.",
            )
        if risk > self.policy.max_risk_allow:
            return GovernanceResult("escalate", risk, reasons or ["medium-risk"])
        return GovernanceResult("allow", risk, reasons or ["low-risk"])

    def evaluate_tool(self, tool_name: str, tool_input: dict, tool_risk: str = "low") -> GovernanceResult:
        """Evaluate a specific tool call for safety.

        This is the heart of HelloAGI's governance — called on EVERY tool invocation.
        """
        reasons: List[str] = []
        risk = TOOL_RISK_BASE.get(tool_risk, 0.1)

        # Serialize tool input for scanning
        input_text = " ".join(str(v) for v in tool_input.values()).lower()

        # Check for dangerous commands in bash/code tools
        if tool_name in ("bash_exec", "python_exec"):
            command = tool_input.get("command", tool_input.get("code", "")).lower()

            for pattern in self.policy.dangerous_command_patterns:
                if pattern in command:
                    risk += 0.8
                    reasons.append(f"dangerous-command:{pattern}")

            for pattern in self.policy.exfil_patterns:
                if pattern.lower() in command:
                    risk += 0.6
                    reasons.append(f"exfil-attempt:{pattern}")

            # Escalate any sudo/admin commands
            if "sudo " in command or "runas" in command:
                risk += 0.3
                reasons.append("privileged-execution:sudo")

            # Escalate network operations
            if any(k in command for k in ["curl ", "wget ", "requests.post", "http.client"]):
                risk += 0.15
                reasons.append("network-operation")

        # Check file operations for sensitive paths
        if tool_name in ("file_write", "file_patch", "file_read"):
            path = tool_input.get("path", "").lower()
            sensitive_paths = ["/etc/", "/root/", ".ssh/", ".env", "credentials", "secrets", ".aws/", "password"]
            for sp in sensitive_paths:
                if sp in path:
                    risk += 0.4
                    reasons.append(f"sensitive-path:{sp}")

        # Check for data exfiltration in web tools
        if tool_name in ("web_fetch", "web_search"):
            url = tool_input.get("url", "").lower()
            query = tool_input.get("query", "").lower()
            combined = url + " " + query
            for pattern in self.policy.exfil_patterns:
                if pattern.lower() in combined:
                    risk += 0.5
                    reasons.append(f"exfil-via-web:{pattern}")

        # General input scanning (applies to all tools)
        for kw in self.policy.deny_keywords:
            if kw in input_text:
                risk += 0.5
                reasons.append(f"deny-keyword-in-tool:{kw}")

        risk = min(risk, 1.0)

        if risk > self.policy.max_risk_escalate:
            return GovernanceResult(
                "deny", risk, reasons or ["high-risk-tool"],
                safe_alternative=f"Tool '{tool_name}' was blocked for safety. Try a different approach.",
            )
        if risk > self.policy.max_risk_allow:
            return GovernanceResult("escalate", risk, reasons or ["medium-risk-tool"])
        return GovernanceResult("allow", risk, reasons or ["low-risk-tool"])
