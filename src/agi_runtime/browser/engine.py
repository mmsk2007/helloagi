"""Browser automation engine — Playwright when installed, HTTP fallback otherwise."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from agi_runtime.browser.governor import BrowserGovernor
from agi_runtime.browser.sandbox import get_sandbox


class BrowserEngine:
    """Navigate and snapshot pages with SSRF checks and per-session state."""

    def __init__(self, settings: Dict[str, Any] | None = None):
        self.settings = settings or {}
        self.headless = bool(self.settings.get("headless", True))
        self._governor = BrowserGovernor(self.settings)
        self._sandbox = get_sandbox()

    def navigate(self, url: str, session_id: str = "default") -> Tuple[bool, str]:
        ok, err = self._governor.check_navigation(url)
        if not ok:
            return False, err
        state = self._sandbox.get(session_id)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return self._navigate_requests(url, state)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                page = browser.new_page()
                page.set_default_timeout(15000)
                page.goto(url, wait_until="domcontentloaded")
                text = page.inner_text("body")[:50000]
                state.url = url
                state.text_snapshot = text
                browser.close()
            return True, text
        except Exception as exc:
            return False, f"Browser error: {exc}"

    def _navigate_requests(self, url: str, state) -> Tuple[bool, str]:
        try:
            import requests
        except ImportError:
            return False, "Neither playwright nor requests is available for browser_navigate"
        try:
            headers = {
                "User-Agent": "HelloAGI-browser-fallback/1.0",
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            }
            resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            resp.raise_for_status()
            raw = resp.text
            try:
                from agi_runtime.tools.builtins.web_fetch import _extract_text_from_html
                text = _extract_text_from_html(raw)[:50000]
            except Exception:
                text = raw[:50000]
            state.url = url
            state.text_snapshot = text
            return True, text
        except Exception as exc:
            return False, f"Fetch fallback failed: {exc}"

    def read_page(self, session_id: str = "default") -> str:
        return self._sandbox.get(session_id).text_snapshot

    def screenshot_path(self, session_id: str = "default") -> Tuple[bool, str]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return False, "Playwright required for browser_screenshot"
        state = self._sandbox.get(session_id)
        if not state.url:
            return False, "No page loaded; call browser_navigate first"
        path = f"memory/browser_{session_id.replace(':', '_')}_shot.png"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                page = browser.new_page()
                page.goto(state.url, wait_until="domcontentloaded")
                page.screenshot(path=path, full_page=False)
                browser.close()
            return True, path
        except Exception as exc:
            return False, str(exc)


_ENGINE: BrowserEngine | None = None


def get_browser_engine(settings: Dict[str, Any] | None = None) -> BrowserEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = BrowserEngine(settings or {})
    return _ENGINE


def reset_browser_engine_for_tests() -> None:
    global _ENGINE
    _ENGINE = None
