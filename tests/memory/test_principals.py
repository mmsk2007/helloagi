import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.core.agent import HelloAGIAgent
from agi_runtime.memory.principals import PrincipalProfileStore


ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / ".tmp-tests"
TMP_ROOT.mkdir(exist_ok=True)


def _make_scratch_dir() -> Path:
    path = TMP_ROOT / f"principals-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


class TestPrincipalProfiles(unittest.TestCase):
    def test_linked_principal_resolves_to_shared_profile(self):
        tmp = _make_scratch_dir()
        try:
            store = PrincipalProfileStore(
                state_path=str(tmp / "principals.json"),
                profiles_dir=str(tmp / "profiles"),
            )
            store.update("local:default", preferred_name="Mohammed", onboarded=True)
            store.link_profile("voice:desktop", "local:default")

            self.assertEqual(store.resolve_profile_id("voice:desktop"), "local:default")
            resolved = store.get("voice:desktop")
            self.assertEqual(resolved.preferred_name, "Mohammed")
            self.assertTrue(resolved.onboarded)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_agent_exposes_current_profile_principal(self):
        tmp = _make_scratch_dir()
        try:
            settings = RuntimeSettings(
                memory_path=str(tmp / "identity_state.json"),
                journal_path=str(tmp / "events.jsonl"),
                db_path=str(tmp / "helloagi.db"),
            )
            agent = HelloAGIAgent(settings)
            agent.principals = PrincipalProfileStore(
                state_path=str(tmp / "principals.json"),
                profiles_dir=str(tmp / "profiles"),
            )
            agent.principals.link_profile("voice:desktop", "local:default")

            agent.set_principal("voice:desktop")
            self.assertEqual(agent.current_principal(), "voice:desktop")
            self.assertEqual(agent.current_profile_principal(), "local:default")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
