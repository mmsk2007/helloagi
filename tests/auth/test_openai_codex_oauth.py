"""Unit tests for OpenAI Codex OAuth helpers (no network)."""

import unittest

from agi_runtime.auth.openai_codex_oauth import _parse_callback_url, _pkce_pair


class TestOpenaiCodexOauth(unittest.TestCase):
    def test_pkce_verifier_and_challenge(self):
        v, c = _pkce_pair()
        self.assertGreaterEqual(len(v), 43)
        self.assertGreater(len(c), 20)

    def test_parse_callback_full_url(self):
        url = "http://127.0.0.1:1455/auth/callback?code=abc&state=xyz"
        code, state = _parse_callback_url(url)
        self.assertEqual(code, "abc")
        self.assertEqual(state, "xyz")

    def test_parse_callback_path_only(self):
        url = "/auth/callback?code=onlycode"
        code, state = _parse_callback_url(url)
        self.assertEqual(code, "onlycode")
        self.assertIsNone(state)


if __name__ == "__main__":
    unittest.main()
