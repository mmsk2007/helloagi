"""Browser-specific policy checks (URL safety, rate hints)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

from agi_runtime.tools.builtins.web_fetch import _check_ssrf


class BrowserGovernor:
    """Lightweight governance before navigation (SRG also gates tools)."""

    def __init__(self, settings: Dict[str, Any] | None = None):
        self.settings = settings or {}
        self._nav_times: List[float] = []

    def check_navigation(self, url: str) -> Tuple[bool, str]:
        ssrf = _check_ssrf(url)
        if ssrf:
            return False, ssrf
        block = self.settings.get("block_hosts", []) or []
        host = ""
        try:
            from urllib.parse import urlparse
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            pass
        for b in block:
            if b and host.endswith(str(b).lower()):
                return False, f"Host blocked by policy: {host}"
        max_per_min = int(self.settings.get("max_nav_per_min", 10))
        now = time.time()
        self._nav_times = [t for t in self._nav_times if now - t < 60.0]
        if len(self._nav_times) >= max_per_min:
            return False, f"Navigation rate limit exceeded ({max_per_min}/min)"
        self._nav_times.append(now)
        return True, ""
