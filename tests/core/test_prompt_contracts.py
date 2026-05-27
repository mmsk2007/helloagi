import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.core.agent import HelloAGIAgent
from agi_runtime.core.personality import GrowthTracker
from agi_runtime.intelligence.patterns import PatternDetector
from agi_runtime.intelligence.sentiment import SentimentTracker
from agi_runtime.memory.principals import PrincipalProfileStore


ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / ".tmp-tests"
TMP_ROOT.mkdir(exist_ok=True)


def _make_scratch_dir() -> Path:
    path = TMP_ROOT / f"prompt-contracts-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


class VoiceChannel:
    pass


class TestPromptContracts(unittest.TestCase):
    def _make_agent(self, tmp: Path) -> HelloAGIAgent:
        settings = RuntimeSettings(
            memory_path=str(tmp / "identity_state.json"),
            journal_path=str(tmp / "events.jsonl"),
            db_path=str(tmp / "helloagi.db"),
        )
        agent = HelloAGIAgent(settings=settings, policy_pack="coder")
        agent.principals = PrincipalProfileStore(
            state_path=str(tmp / "principals.json"),
            profiles_dir=str(tmp / "profiles"),
        )
        agent.growth = GrowthTracker(path=str(tmp / "growth.json"))
        agent.sentiment = SentimentTracker(path=str(tmp / "mood.json"))
        agent.patterns = PatternDetector(path=str(tmp / "patterns.json"))
        return agent

    def test_system_prompt_includes_active_task_and_response_contract(self):
        tmp = _make_scratch_dir()
        try:
            agent = self._make_agent(tmp)
            agent._history = [
                {"role": "user", "content": "Build a Telegram task status flow for long jobs."},
                {"role": "assistant", "content": "I can do that."},
                {"role": "user", "content": "continue"},
            ]
            agent.set_active_channel(VoiceChannel(), "voice:test")

            prompt = agent._build_system_prompt()

            self.assertIn("<policy-pack>", prompt)
            self.assertIn("Traits to embody: precise, test-driven, security-aware, pragmatic.", prompt)
            self.assertIn("<operating-rules>", prompt)
            self.assertIn("Short replies like 'continue', 'yes', or 'do it' usually mean continue the active task", prompt)
            self.assertIn("<response-contract>", prompt)
            self.assertIn("latency is user-visible", prompt)
            self.assertIn("<active-task>", prompt)
            self.assertIn("Current objective: Build a Telegram task status flow for long jobs.", prompt)
            self.assertIn("Latest user message: continue", prompt)
            self.assertIn("Latest user message is a continuation or approval.", prompt)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_system_prompt_includes_context_unrolling_action_gate(self):
        tmp = _make_scratch_dir()
        try:
            agent = self._make_agent(tmp)

            prompt = agent._build_system_prompt()

            self.assertIn("<context-unrolling>", prompt)
            self.assertIn("typed intermediate workspace", prompt)
            self.assertIn("observed evidence from generated assumptions", prompt)
            self.assertIn("verify generated assumptions before high-risk or irreversible tool calls", prompt)
            self.assertIn("</context-unrolling>", prompt)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_tool_execution_records_context_workspace_evidence(self):
        tmp = _make_scratch_dir()
        try:
            agent = self._make_agent(tmp)

            class Governance:
                decision = "allow"
                risk = 0.1

            class Result:
                ok = True

                def to_content(self):
                    return "read 3 lines"

            agent._record_tool_context_workspace(
                user_input="Read docs/context-unrolling.md and summarize the verified parts.",
                tool_call={"name": "file_read", "input": {"path": "docs/context-unrolling.md"}},
                tool_governance=Governance(),
                result=Result(),
                provider="test",
            )

            events = [line for line in (tmp / "events.jsonl").read_text().splitlines() if line]
            self.assertEqual(len(events), 1)
            self.assertIn('"kind": "context_workspace_tool_evidence"', events[0])
            self.assertIn('"type": "user_request"', events[0])
            self.assertIn('"type": "generated_tool_call"', events[0])
            self.assertIn('"type": "governance_verification"', events[0])
            self.assertIn('"type": "tool_evidence"', events[0])
            self.assertIn('"observed": true', events[0])
            self.assertIn('"verified": true', events[0])
            event = json.loads(events[0])
            generated = event["payload"]["workspace"]["items"][1]
            self.assertEqual(generated["content"], {"tool": "file_read", "input_keys": ["path"]})
            self.assertNotIn("docs/context-unrolling.md", json.dumps(generated["content"]))
            self.assertNotIn("docs/context-unrolling.md", events[0])
            self.assertNotIn("Read docs/context-unrolling.md", events[0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_escalated_tool_context_records_user_approval_as_verification(self):
        tmp = _make_scratch_dir()
        try:
            agent = self._make_agent(tmp)

            class Governance:
                decision = "escalate"
                risk = 0.72

            class Result:
                ok = True

                def to_content(self):
                    return "wrote file"

            agent._record_tool_context_workspace(
                user_input="Update the selected config file after approval.",
                tool_call={"name": "file_write", "input": {"path": "public/config.toml", "content": "safe"}},
                tool_governance=Governance(),
                result=Result(),
                provider="test",
                user_approved=True,
            )

            event = json.loads((tmp / "events.jsonl").read_text().splitlines()[0])
            payload = event["payload"]
            self.assertTrue(payload["action_ready"])
            self.assertEqual(payload["action_gate"], "ready")
            item_types = [item["type"] for item in payload["workspace"]["items"]]
            self.assertIn("action_risk", item_types)
            self.assertIn("scope", item_types)
            self.assertIn("user_approval_verification", item_types)
            generated = next(item for item in payload["workspace"]["items"] if item["type"] == "generated_tool_call")
            self.assertTrue(generated["verified"])
            self.assertNotIn("public/config.toml", json.dumps(payload))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_gemini_tool_execution_records_context_workspace_evidence(self):
        source = Path(HelloAGIAgent._think_async_gemini.__code__.co_filename).read_text()
        gemini_body = source[source.index("    async def _think_async_gemini"):]

        self.assertIn("_record_tool_context_workspace", gemini_body)
        self.assertIn('provider="google"', gemini_body)
        self.assertIn("user_approved=user_approved", gemini_body)
        self.assertIn('"provider": "google"', gemini_body)

    def test_sub_agent_prompt_is_execution_focused(self):
        tmp = _make_scratch_dir()
        try:
            agent = self._make_agent(tmp)

            prompt = agent._build_sub_agent_system_prompt(
                goal="Investigate why Telegram progress updates stall",
                context="Use existing channel callbacks and do not change unrelated voice code.",
                max_turns=25,
            )

            self.assertIn("You are an execution sub-agent", prompt)
            self.assertIn("You are not the primary conversational assistant.", prompt)
            self.assertIn("Stay narrowly focused on the delegated goal.", prompt)
            self.assertIn("Do not add personality filler, onboarding, or general chat.", prompt)
            self.assertIn("Goal: Investigate why Telegram progress updates stall", prompt)
            self.assertIn("Context: Use existing channel callbacks and do not change unrelated voice code.", prompt)
            self.assertIn("Turn budget: at most 15 turns.", prompt)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
