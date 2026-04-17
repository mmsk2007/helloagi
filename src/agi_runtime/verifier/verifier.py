"""LLM-powered outcome verifier.

Validates execution results against the original goal.
Returns structured verdict: PASS / PARTIAL / FAIL.
On PARTIAL/FAIL, provides suggestions for re-planning.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


@dataclass
class VerifyResult:
    passed: bool
    status: str  # "PASS" | "PARTIAL" | "FAIL"
    summary: str
    suggestions: List[str] = field(default_factory=list)
    confidence: float = 0.0  # 0-1 how confident we are in the verdict


class Verifier:
    """Verify execution results against the original goal."""

    VERIFY_PROMPT = """You are a verification agent. Given a goal and execution outputs, determine if the goal was achieved.

Goal: {goal}

Execution outputs:
{outputs}

Respond with ONLY a JSON object:
{{
  "status": "PASS" or "PARTIAL" or "FAIL",
  "summary": "brief explanation of what was achieved",
  "suggestions": ["list of suggestions if not fully achieved"],
  "confidence": 0.0 to 1.0
}}

Be honest and precise. PASS means the goal is fully achieved. PARTIAL means some progress. FAIL means no meaningful progress."""

    def check(self, outputs: list[str], goal: str) -> VerifyResult:
        """Verify outputs against goal using LLM or heuristics."""
        if not outputs:
            return VerifyResult(
                passed=False,
                status="FAIL",
                summary="No outputs produced.",
                suggestions=["Re-examine the plan and ensure steps produce outputs."],
            )

        # Try LLM verification
        if _ANTHROPIC_AVAILABLE and os.environ.get("ANTHROPIC_API_KEY"):
            return self._llm_verify(outputs, goal)

        # Fallback to heuristic verification
        return self._heuristic_verify(outputs, goal)

    def _llm_verify(self, outputs: list[str], goal: str) -> VerifyResult:
        try:
            client = anthropic.Anthropic()
            outputs_text = "\n---\n".join(
                f"Step {i+1}: {o[:500]}" for i, o in enumerate(outputs)
            )

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": self.VERIFY_PROMPT.format(goal=goal, outputs=outputs_text),
                }],
            )

            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            data = json.loads(text)
            status = data.get("status", "FAIL")

            return VerifyResult(
                passed=status == "PASS",
                status=status,
                summary=data.get("summary", ""),
                suggestions=data.get("suggestions", []),
                confidence=data.get("confidence", 0.5),
            )

        except Exception as e:
            return self._heuristic_verify(outputs, goal)

    def _heuristic_verify(self, outputs: list[str], goal: str) -> VerifyResult:
        """Simple heuristic verification when LLM is unavailable."""
        # Check for error indicators
        error_count = sum(1 for o in outputs if "error" in o.lower() or "failed" in o.lower())
        success_count = sum(1 for o in outputs if o and "error" not in o.lower())

        if error_count == 0 and success_count == len(outputs):
            return VerifyResult(
                passed=True,
                status="PASS",
                summary=f"All {len(outputs)} steps completed without errors.",
                confidence=0.6,
            )
        elif success_count > error_count:
            return VerifyResult(
                passed=False,
                status="PARTIAL",
                summary=f"{success_count}/{len(outputs)} steps succeeded, {error_count} had errors.",
                suggestions=["Review and retry failed steps."],
                confidence=0.4,
            )
        else:
            return VerifyResult(
                passed=False,
                status="FAIL",
                summary=f"Most steps failed ({error_count}/{len(outputs)} errors).",
                suggestions=["Re-examine approach. Consider alternative tools or methods."],
                confidence=0.3,
            )
