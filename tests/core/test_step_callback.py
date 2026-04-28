"""step_callback is invoked after each LLM parse (Hermes-style telemetry hook)."""

from unittest.mock import MagicMock

import pytest

from agi_runtime.core.agent import HelloAGIAgent, ToolCall


@pytest.fixture
def agent():
    return HelloAGIAgent()


def test_step_callback_fires_with_planned_tools(agent: HelloAGIAgent):
    steps = []

    def step_cb(turn, planned):
        steps.append((turn, [p["name"] for p in planned]))

    agent.step_callback = step_cb
    agent._emit_step_callback(3, [])
    agent._emit_step_callback(
        4,
        [ToolCall(id="1", name="web_search", input={"q": "x"})],
    )
    assert steps == [(3, []), (4, ["web_search"])]


def test_step_callback_swallows_exceptions(agent: HelloAGIAgent):
    agent.step_callback = MagicMock(side_effect=RuntimeError("boom"))
    agent._emit_step_callback(1, [])
