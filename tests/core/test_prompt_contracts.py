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
