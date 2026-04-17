"""Fetch a URL and extract clean text content."""

import os

from agi_runtime.tools.registry import tool, ToolParam, ToolResult


@tool(
    name="web_fetch",
    description="Fetch a URL and extract its main text content. Strips HTML tags and returns clean readable text.",
    toolset="web",
    risk="low",
    parameters=[
        ToolParam("url", "string", "The URL to fetch"),
        ToolParam("max_length", "integer", "Maximum characters to return", required=False, default=10000),
    ],
)
def web_fetch(url: str, max_length: int = 10000) -> ToolResult:
    # SSRF protection: block internal/private network addresses
    ssrf_error = _check_ssrf(url)
    if ssrf_error:
        return ToolResult(ok=False, output="", error=ssrf_error)

    try:
        import requests
    except ImportError:
        return ToolResult(ok=False, output="", error="requests library not installed. Run: pip install requests")

    try:
        headers = {
            "User-Agent": "HelloAGI/1.0 (autonomous agent; +https://github.com/helloagi)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")

        # If JSON, return formatted
        if "application/json" in content_type:
            import json
            try:
                data = resp.json()
                text = json.dumps(data, indent=2, ensure_ascii=False)
            except Exception:
                text = resp.text
        # If plain text, return directly
        elif "text/plain" in content_type:
            text = resp.text
        else:
            # HTML — extract text
            text = _extract_text_from_html(resp.text)

        if len(text) > max_length:
            text = text[:max_length] + "\n... (truncated)"

        return ToolResult(ok=True, output=text)

    except Exception as e:
        return ToolResult(ok=False, output="", error=f"Fetch failed: {e}")


def _check_ssrf(url: str) -> str:
    """Block requests to internal/private network addresses."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        host = parsed.hostname or ""

        if scheme not in ("http", "https"):
            return f"Blocked: only http/https schemes allowed, got '{scheme}'"

        # Block obviously internal hostnames
        blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}
        if host.lower() in blocked_hosts:
            return f"Blocked: cannot fetch internal address '{host}'"

        # Block private IP ranges
        import ipaddress
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return f"Blocked: cannot fetch private/internal IP '{host}'"
        except ValueError:
            pass  # hostname, not IP — OK

        # Block internal-looking hostnames
        if host.endswith(".local") or host.endswith(".internal"):
            return f"Blocked: cannot fetch internal hostname '{host}'"

    except Exception:
        return "Blocked: failed to parse URL"

    return ""  # No SSRF risk detected


def _extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML, stripping tags and scripts."""
    try:
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts = []
                self._skip = False
                self._skip_tags = {"script", "style", "nav", "footer", "header"}

            def handle_starttag(self, tag, attrs):
                if tag in self._skip_tags:
                    self._skip = True

            def handle_endtag(self, tag):
                if tag in self._skip_tags:
                    self._skip = False
                if tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
                    self.parts.append("\n")

            def handle_data(self, data):
                if not self._skip:
                    text = data.strip()
                    if text:
                        self.parts.append(text + " ")

        extractor = TextExtractor()
        extractor.feed(html)
        text = "".join(extractor.parts)

        # Clean up whitespace
        import re
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    except Exception:
        # Fallback: crude tag stripping
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
