"""LLMCouncilAgent — JSON parsing + abstain-on-error tests.

We never make real LLM calls in tests. ``FakeClient`` mimics the
Anthropic SDK shape (``messages.create`` → object with ``.content``
list of blocks); we test that:
- well-formed JSON parses into structured AgentTurn fields
- malformed JSON gracefully abstains (instead of raising)
- vote alphabet is enforced — anything outside yes/no/abstain → abstain
- confidence is clamped 0-1
- client errors abstain, don't crash
"""

import unittest
from dataclasses import dataclass

from agi_runtime.cognition.system2 import (
    LLMCouncilAgent,
    PLANNER_ROLE,
    make_default_roster,
)
from agi_runtime.cognition.system2.agents import PLANNER_PROMPT


@dataclass
class _Block:
    type: str = "text"
    text: str = ""


class _Response:
    def __init__(self, text: str):
        self.content = [_Block(type="text", text=text)]


class _FakeMessages:
    def __init__(self, response_text: str = "", raises: Exception = None):
        self._text = response_text
        self._raises = raises

    def create(self, **kwargs):
        if self._raises is not None:
            raise self._raises
        return _Response(self._text)


class _FakeClient:
    def __init__(self, response_text: str = "", raises: Exception = None):
        self.messages = _FakeMessages(response_text=response_text, raises=raises)


class TestLLMAgentParsing(unittest.TestCase):
    def _agent(self, response_text: str = "", raises: Exception = None) -> LLMCouncilAgent:
        return LLMCouncilAgent(
            name="planner",
            role=PLANNER_ROLE,
            role_prompt=PLANNER_PROMPT,
            client=_FakeClient(response_text=response_text, raises=raises),
        )

    def test_well_formed_json_parses(self):
        agent = self._agent('{"plan": "step 1; step 2", "vote": "yes", "confidence": 0.9, "suggested_tools": ["browser_navigate"]}')
        turn = agent.respond(user_input="task", prior_rounds=[])
        self.assertEqual(turn.vote, "yes")
        self.assertEqual(turn.confidence, 0.9)
        self.assertEqual(turn.suggested_tools, ["browser_navigate"])
        self.assertIn("step 1", turn.output)
        self.assertEqual(turn.agent, "planner")
        self.assertEqual(turn.role, PLANNER_ROLE)

    def test_json_inside_prose_is_extracted(self):
        agent = self._agent('Sure, here is my plan:\n{"plan": "x", "vote": "yes", "confidence": 0.5}\nLet me know.')
        turn = agent.respond(user_input="task", prior_rounds=[])
        self.assertEqual(turn.vote, "yes")
        self.assertEqual(turn.output, "x")

    def test_no_json_abstains(self):
        agent = self._agent("I have no opinion on this matter.")
        turn = agent.respond(user_input="task", prior_rounds=[])
        self.assertEqual(turn.vote, "abstain")
        self.assertIn("no_json", turn.critique)

    def test_invalid_vote_falls_back_to_abstain(self):
        agent = self._agent('{"plan": "x", "vote": "maybe", "confidence": 0.7}')
        turn = agent.respond(user_input="task", prior_rounds=[])
        self.assertEqual(turn.vote, "abstain")

    def test_confidence_is_clamped(self):
        agent = self._agent('{"plan": "x", "vote": "yes", "confidence": 99}')
        turn = agent.respond(user_input="task", prior_rounds=[])
        self.assertLessEqual(turn.confidence, 1.0)

    def test_client_error_abstains(self):
        agent = self._agent(raises=RuntimeError("network"))
        turn = agent.respond(user_input="task", prior_rounds=[])
        self.assertEqual(turn.vote, "abstain")
        self.assertIn("client_error", turn.critique)

    def test_malformed_json_abstains(self):
        agent = self._agent("{not valid json}")
        turn = agent.respond(user_input="task", prior_rounds=[])
        self.assertEqual(turn.vote, "abstain")


class TestDefaultRoster(unittest.TestCase):
    def test_default_roster_has_four_roles(self):
        roster = make_default_roster(_FakeClient())
        names = [a.name for a in roster]
        self.assertEqual(
            sorted(names), ["critic", "planner", "risk_auditor", "synthesizer"]
        )


if __name__ == "__main__":
    unittest.main()
