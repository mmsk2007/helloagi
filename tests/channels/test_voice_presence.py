import unittest

from agi_runtime.api.server import _voice_monitor_html
from agi_runtime.channels.voice_presence import VoicePresenceStore


class TestVoicePresenceStore(unittest.TestCase):
    def test_update_increments_version(self):
        store = VoicePresenceStore()
        before = store.snapshot()
        after = store.update(state="listening", detail="say lana", active=True)
        self.assertGreater(after["version"], before["version"])
        self.assertEqual(after["state"], "listening")
        self.assertTrue(after["active"])

    def test_wait_for_change_returns_new_snapshot(self):
        store = VoicePresenceStore()
        first = store.snapshot()
        store.update(state="speaking", detail="hello", last_spoken="hello")
        changed = store.wait_for_change(first["version"], timeout=0.01)
        self.assertIsNotNone(changed)
        self.assertEqual(changed["state"], "speaking")


class TestVoiceMonitorHtml(unittest.TestCase):
    def test_monitor_page_mentions_voice_stream(self):
        html = _voice_monitor_html(auth_required=False)
        self.assertIn("/voice/events", html)
        self.assertIn("Voice Monitor", html)
