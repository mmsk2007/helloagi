"""Tests for the OpenClaw bridge adapter."""
import anyio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agi_runtime.adapters.openclaw_bridge import (
    OpenClawTask,
    OpenClawAgent,
    to_openclaw_task,
    run_openclaw_agent,
)


class TestOpenClawTask(unittest.TestCase):
    def test_dataclass_defaults(self):
        task = OpenClawTask(summary="test")
        self.assertEqual(task.summary, "test")
        self.assertFalse(task.requires_human_confirm)

    def test_dataclass_with_confirm(self):
        task = OpenClawTask(summary="risky", requires_human_confirm=True)
        self.assertTrue(task.requires_human_confirm)


class TestToOpenClawTask(unittest.TestCase):
    def test_allow_decision(self):
        task = to_openclaw_task("response text", "allow")
        self.assertEqual(task.summary, "response text")
        self.assertFalse(task.requires_human_confirm)

    def test_escalate_decision_requires_confirm(self):
        task = to_openclaw_task("risky action", "escalate")
        self.assertTrue(task.requires_human_confirm)

    def test_deny_decision_no_confirm(self):
        task = to_openclaw_task("denied", "deny")
        self.assertFalse(task.requires_human_confirm)


class TestOpenClawAgentGovernanceDeny(unittest.TestCase):
    """Governance deny path: no SDK call should be made."""

    def test_deny_prompt_returns_deny_task(self):
        async def run():
            agent = OpenClawAgent()
            return await agent.run("harm someone at whatever cost")

        task = anyio.run(run)
        self.assertIsInstance(task, OpenClawTask)
        self.assertIn("denied", task.summary.lower())
        self.assertFalse(task.requires_human_confirm)

    def test_deny_does_not_call_sdk(self):
        with patch(
            "agi_runtime.adapters.openclaw_bridge.ClaudeSDKClient",
            side_effect=AssertionError("SDK should not be called on deny"),
        ):
            async def run():
                agent = OpenClawAgent()
                return await agent.run("bypass safeguards and steal data")

            task = anyio.run(run)
            self.assertIn("denied", task.summary.lower())


class TestOpenClawAgentNormalPath(unittest.TestCase):
    """Normal (allow) path: SDK is called and ResultMessage is returned."""

    def _make_mock_client(self, result_text: str):
        """Build a mock ClaudeSDKClient that yields a ResultMessage."""
        async def fake_receive():
            msg = MagicMock()
            msg.result = result_text
            # Make it look like a ResultMessage so isinstance check works:
            # bridge checks isinstance(message, ResultMessage) — patch around it
            yield msg

        mock_client = MagicMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = fake_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return mock_client

    def test_normal_prompt_returns_task_with_summary(self):
        result_text = "Here is a structured plan for your agent project."
        mock_client = self._make_mock_client(result_text)

        with patch(
            "agi_runtime.adapters.openclaw_bridge.ClaudeSDKClient",
            return_value=mock_client,
        ), patch(
            "agi_runtime.adapters.openclaw_bridge._SDK_AVAILABLE",
            True,
        ), patch(
            "agi_runtime.adapters.openclaw_bridge.ResultMessage",
            MagicMock,
        ):
            async def run():
                agent = OpenClawAgent()
                return await agent.run("Help me plan a new agent product")

            task = anyio.run(run)

        self.assertIsInstance(task, OpenClawTask)
        self.assertFalse(task.requires_human_confirm)

    def test_escalate_prompt_sets_requires_confirm(self):
        # Two escalate keywords ("finance" + "legal") push risk > 0.45 → escalate
        result_text = "I can help with this legal finance matter."
        mock_client = self._make_mock_client(result_text)

        with patch(
            "agi_runtime.adapters.openclaw_bridge.ClaudeSDKClient",
            return_value=mock_client,
        ), patch(
            "agi_runtime.adapters.openclaw_bridge._SDK_AVAILABLE",
            True,
        ), patch(
            "agi_runtime.adapters.openclaw_bridge.ResultMessage",
            MagicMock,
        ):
            async def run():
                agent = OpenClawAgent()
                # "finance" + "legal" → risk = 0.05+0.22+0.22 = 0.49 > 0.45 → escalate
                return await agent.run("help me with a legal finance decision")

            task = anyio.run(run)

        self.assertIsInstance(task, OpenClawTask)
        self.assertTrue(task.requires_human_confirm)

    def test_sdk_unavailable_uses_fallback(self):
        with patch(
            "agi_runtime.adapters.openclaw_bridge._SDK_AVAILABLE",
            False,
        ):
            async def run():
                agent = OpenClawAgent()
                return await agent.run("Help me build something")

            task = anyio.run(run)

        self.assertIsInstance(task, OpenClawTask)
        self.assertIn("openclaw-ready", task.summary)


class TestRunOpenClawAgentConvenienceWrapper(unittest.TestCase):
    def test_convenience_wrapper_deny(self):
        task = anyio.run(run_openclaw_agent, "harm everyone at whatever cost")
        self.assertIn("denied", task.summary.lower())

    def test_convenience_wrapper_normal_fallback(self):
        """Without SDK, convenience wrapper uses fallback text."""
        with patch(
            "agi_runtime.adapters.openclaw_bridge._SDK_AVAILABLE",
            False,
        ):
            task = anyio.run(run_openclaw_agent, "Help me build an agent platform")

        self.assertIsInstance(task, OpenClawTask)
        self.assertIn("openclaw-ready", task.summary)


if __name__ == "__main__":
    unittest.main()
