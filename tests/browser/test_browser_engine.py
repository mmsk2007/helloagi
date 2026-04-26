import unittest
from unittest.mock import MagicMock, patch

from agi_runtime.browser.engine import BrowserEngine, reset_browser_engine_for_tests


class TestBrowserEngine(unittest.TestCase):
    def tearDown(self) -> None:
        reset_browser_engine_for_tests()

    def test_navigate_blocked_ssrf(self) -> None:
        eng = BrowserEngine({})
        ok, msg = eng.navigate("http://127.0.0.1/", "s")
        self.assertFalse(ok)
        self.assertIn("Blocked", msg)

    @patch("requests.get")
    def test_navigate_requests_fallback(self, mock_get) -> None:
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>HelloAGI</body></html>"
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        eng = BrowserEngine({})
        state = eng._sandbox.get("sid")
        ok, text = eng._navigate_requests("https://example.com", state)
        self.assertTrue(ok)
        self.assertIn("HelloAGI", text)


if __name__ == "__main__":
    unittest.main()
