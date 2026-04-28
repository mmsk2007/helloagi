"""LLM-backed council agent.

Wraps an Anthropic Messages-API client behind the ``CouncilAgent``
protocol. One instance per role (Planner, Critic, Risk Auditor,
Synthesizer); each carries its own role prompt.

The agent asks Claude for **JSON output** so we can populate the
``AgentTurn`` fields deterministically. If parsing fails (model returns
prose, or the SDK errors), the agent abstains rather than crashing — the
council should degrade to whatever agents *did* respond, not blow up the
whole think() call.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, List, Optional

from agi_runtime.cognition.trace import DebateRound
from agi_runtime.cognition.system2.agents import (
    AgentTurn,
    CRITIC_PROMPT,
    CRITIC_ROLE,
    PLANNER_PROMPT,
    PLANNER_ROLE,
    RISK_AUDITOR_PROMPT,
    RISK_AUDITOR_ROLE,
    SYNTHESIZER_PROMPT,
    SYNTHESIZER_ROLE,
)


# Council agents run on the cheap-fast model by default. Synthesizer can be
# upgraded to Sonnet via the factory if the user wants better tie-breaking.
DEFAULT_COUNCIL_MODEL = "claude-haiku-4-5-20251001"
SYNTHESIZER_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS = 700


@dataclass
class LLMCouncilAgent:
    """A single LLM-driven role on the council.

    ``client`` is duck-typed: anything with ``.messages.create(...)``
    matching the Anthropic SDK shape works. We don't import the SDK here
    so the cognition package stays loosely coupled — the agent factory
    in ``factory.py`` does the SDK binding.
    """

    name: str
    role: str
    role_prompt: str
    client: Any
    model: str = DEFAULT_COUNCIL_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS

    def respond(self, *, user_input: str, prior_rounds: List[DebateRound]) -> AgentTurn:
        prompt = _build_user_message(user_input=user_input, prior_rounds=prior_rounds)
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.role_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            return _abstain(self.name, self.role, reason=f"client_error:{type(e).__name__}")

        text = _extract_text(response)
        return _parse_turn(self.name, self.role, text)


def _build_user_message(*, user_input: str, prior_rounds: List[DebateRound]) -> str:
    parts = [f"USER TASK:\n{user_input}\n"]
    if prior_rounds:
        parts.append("\nPRIOR ROUNDS:")
        for r in prior_rounds[-2:]:  # last 2 rounds to keep tokens bounded
            parts.append(f"\n— Round {r.round_index}:")
            for name, output in r.agent_outputs.items():
                preview = (output or "")[:400]
                parts.append(f"  • {name}: {preview}")
            if r.critiques:
                parts.append(f"  • critiques: {' | '.join(r.critiques[:3])}")
    parts.append(
        "\nReturn JSON only — no prose around the JSON. Required keys per "
        "your role prompt. ``vote`` must be one of: yes, no, abstain. "
        "``confidence`` must be a number 0-1."
    )
    return "\n".join(parts)


def _extract_text(response: Any) -> str:
    """Pull text from an Anthropic Messages API response object.

    Falls back to ``str(response)`` if the structure isn't recognized —
    which simply means JSON parsing will fail and the agent will abstain.
    """
    try:
        for block in getattr(response, "content", []):
            if getattr(block, "type", "") == "text":
                return getattr(block, "text", "") or ""
    except Exception:
        pass
    return ""


_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


def _parse_turn(name: str, role: str, text: str) -> AgentTurn:
    if not text:
        return _abstain(name, role, reason="empty_response")
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return _abstain(name, role, reason="no_json")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return _abstain(name, role, reason="bad_json")
    if not isinstance(data, dict):
        return _abstain(name, role, reason="not_object")

    vote = str(data.get("vote", "abstain")).strip().lower()
    if vote not in ("yes", "no", "abstain"):
        vote = "abstain"

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    output = data.get("output") or data.get("plan") or data.get("final_decision") or ""
    if not isinstance(output, str):
        output = json.dumps(output)

    critique = str(data.get("critique") or data.get("risk_summary") or "")
    suggested_tools_raw = data.get("suggested_tools") or []
    if not isinstance(suggested_tools_raw, list):
        suggested_tools_raw = []
    suggested_tools = [str(t) for t in suggested_tools_raw if t]

    return AgentTurn(
        agent=name,
        role=role,
        output=output.strip(),
        vote=vote,
        confidence=confidence,
        suggested_tools=suggested_tools,
        critique=critique.strip(),
    )


def _abstain(name: str, role: str, *, reason: str) -> AgentTurn:
    return AgentTurn(
        agent=name,
        role=role,
        output="",
        vote="abstain",
        confidence=0.0,
        critique=f"abstained:{reason}",
    )


def make_default_roster(
    client: Any,
    *,
    model: str = DEFAULT_COUNCIL_MODEL,
    synthesizer_model: Optional[str] = None,
) -> List[LLMCouncilAgent]:
    """Build the canonical four-agent council bound to a Claude client."""
    synth_model = synthesizer_model or SYNTHESIZER_DEFAULT_MODEL
    return [
        LLMCouncilAgent(
            name="planner",
            role=PLANNER_ROLE,
            role_prompt=PLANNER_PROMPT,
            client=client,
            model=model,
        ),
        LLMCouncilAgent(
            name="critic",
            role=CRITIC_ROLE,
            role_prompt=CRITIC_PROMPT,
            client=client,
            model=model,
        ),
        LLMCouncilAgent(
            name="risk_auditor",
            role=RISK_AUDITOR_ROLE,
            role_prompt=RISK_AUDITOR_PROMPT,
            client=client,
            model=model,
        ),
        LLMCouncilAgent(
            name="synthesizer",
            role=SYNTHESIZER_ROLE,
            role_prompt=SYNTHESIZER_PROMPT,
            client=client,
            model=synth_model,
        ),
    ]


__all__ = [
    "LLMCouncilAgent",
    "make_default_roster",
    "DEFAULT_COUNCIL_MODEL",
    "SYNTHESIZER_DEFAULT_MODEL",
]
