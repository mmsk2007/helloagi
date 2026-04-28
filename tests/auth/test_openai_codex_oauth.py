"""Unit tests for OpenAI Codex OAuth helpers (no network)."""

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

from agi_runtime.auth.openai_codex_oauth import (
    _jwt_exp_unix,
    _parse_callback_url,
    _pkce_pair,
    import_codex_auth_json,
)


def _minimal_jwt_like_token(*, exp: int = 2000000000) -> str:
    """Build a 3-segment token with a decodable payload (no static JWT-shaped literals for secret scanners)."""
    payload = json.dumps({"exp": exp}, separators=(",", ":"))
    seg = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    return "h." + seg + ".s"


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

    def test_jwt_exp_decode(self):
        token = _minimal_jwt_like_token(exp=2000000000)
        self.assertEqual(_jwt_exp_unix(token), 2000000000.0)

    def test_import_codex_nested_tokens(self):
        with tempfile.TemporaryDirectory() as d:
            store = Path(d) / "oauth_store.json"
            os.environ["HELLOAGI_OPENAI_OAUTH_STORE"] = str(store)
            try:
                p = Path(d) / "auth.json"
                access = "t." + _minimal_jwt_like_token(exp=2000000000).split(".", 2)[1] + ".z"
                p.write_text(
                    json.dumps(
                        {
                            "tokens": {
                                "access_token": access,
                                "refresh_token": "refresh-xyz",
                            },
                            "client_id": "app_testclientidhere12",
                        }
                    ),
                    encoding="utf-8",
                )
                r = import_codex_auth_json(p)
                self.assertEqual(r.refresh_token, "refresh-xyz")
                self.assertTrue(r.access_token.startswith("t."))
                self.assertTrue(store.is_file())
            finally:
                os.environ.pop("HELLOAGI_OPENAI_OAUTH_STORE", None)


if __name__ == "__main__":
    unittest.main()
