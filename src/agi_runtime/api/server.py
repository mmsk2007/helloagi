"""HelloAGI HTTP API — Production-grade server with SSE streaming.

Endpoints:
  GET  /health      — Detailed health with subsystem status
  POST /chat        — Chat with the agent (supports SSE streaming)
  GET  /tools       — List available tools with schemas
  GET  /skills      — List learned skills
  GET  /identity    — Agent identity and principles
  GET  /sessions    — Session info
  GET  /governance  — SRG governance stats
"""

from __future__ import annotations

import json
import os
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from agi_runtime.core.agent import HelloAGIAgent
from agi_runtime.config.settings import RuntimeSettings, load_settings


class HelloAGIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the HelloAGI API."""

    agent: HelloAGIAgent = None
    api_key: str = None
    _stats = {"requests": 0, "started_at": time.time()}

    def log_message(self, format, *args):
        """Suppress default logging — use journal instead."""
        pass

    def _check_auth(self) -> bool:
        """Check API key if configured."""
        if not self.api_key:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:] == self.api_key
        return self.headers.get("X-API-Key", "") == self.api_key

    def _send_json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        self.__class__._stats["requests"] += 1
        path = urlparse(self.path).path

        if not self._check_auth():
            return self._send_json(401, {"error": "unauthorized"})

        if path == "/health":
            return self._handle_health()
        elif path == "/tools":
            return self._handle_tools()
        elif path == "/skills":
            return self._handle_skills()
        elif path == "/identity":
            return self._handle_identity()
        elif path == "/governance":
            return self._handle_governance()
        else:
            return self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        self.__class__._stats["requests"] += 1

        if not self._check_auth():
            return self._send_json(401, {"error": "unauthorized"})

        path = urlparse(self.path).path
        if path == "/chat":
            return self._handle_chat()
        elif path == "/chat/stream":
            return self._handle_chat_stream()
        else:
            return self._send_json(404, {"error": "not_found"})

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n) if n > 0 else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # ── Endpoint Handlers ─────────────────────────────────────

    def _handle_health(self):
        uptime = time.time() - self._stats["started_at"]
        tools = self.agent.tool_registry.list_tools()
        self._send_json(200, {
            "ok": True,
            "service": "helloagi",
            "version": "0.5.0",
            "agent": self.agent.identity.state.name,
            "tools": len(tools),
            "skills": len(self.agent.skills.list_skills()),
            "llm_configured": self.agent._claude is not None,
            "srg_active": True,
            "uptime_seconds": round(uptime),
            "total_requests": self._stats["requests"],
        })

    def _handle_tools(self):
        tools = self.agent.tool_registry.list_tools()
        tool_list = []
        for t in sorted(tools, key=lambda x: (x.toolset.value, x.name)):
            tool_list.append({
                "name": t.name,
                "description": t.description,
                "toolset": t.toolset.value,
                "risk": t.risk.value,
                "parameters": [
                    {"name": p.name, "type": p.type, "description": p.description, "required": p.required}
                    for p in t.parameters
                ],
            })
        self._send_json(200, {"tools": tool_list, "count": len(tool_list)})

    def _handle_skills(self):
        skills = self.agent.skills.list_skills()
        skill_list = [
            {
                "name": s.name,
                "description": s.description,
                "triggers": s.triggers,
                "tools": s.tools,
                "invoke_count": s.invoke_count,
            }
            for s in skills
        ]
        self._send_json(200, {"skills": skill_list, "count": len(skill_list)})

    def _handle_identity(self):
        state = self.agent.identity.state
        self._send_json(200, {
            "name": state.name,
            "character": state.character,
            "purpose": state.purpose,
            "principles": state.principles,
        })

    def _handle_governance(self):
        """Return governance configuration and stats."""
        policy = self.agent.governor.policy
        self._send_json(200, {
            "srg_active": True,
            "deny_keywords": policy.deny_keywords,
            "escalate_keywords": policy.escalate_keywords,
            "thresholds": {
                "max_risk_allow": policy.max_risk_allow,
                "max_risk_escalate": policy.max_risk_escalate,
            },
            "dangerous_patterns_count": len(policy.dangerous_command_patterns),
            "exfil_patterns_count": len(policy.exfil_patterns),
        })

    def _handle_chat(self):
        """Non-streaming chat endpoint."""
        data = self._read_body()
        msg = data.get("message", "")
        if not msg:
            return self._send_json(400, {"error": "missing 'message' field"})

        start = time.time()
        r = self.agent.think(msg)
        elapsed = time.time() - start

        self._send_json(200, {
            "response": r.text,
            "decision": r.decision,
            "risk": r.risk,
            "tool_calls": r.tool_calls_made,
            "turns": r.turns_used,
            "elapsed_ms": round(elapsed * 1000),
        })

    def _handle_chat_stream(self):
        """SSE streaming chat endpoint."""
        data = self._read_body()
        msg = data.get("message", "")
        if not msg:
            return self._send_json(400, {"error": "missing 'message' field"})

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        def send_event(event_type: str, data: dict):
            payload = json.dumps(data, ensure_ascii=False)
            self.wfile.write(f"event: {event_type}\ndata: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()

        # Wire callbacks for streaming
        original_tool_start = self.agent.on_tool_start
        original_tool_end = self.agent.on_tool_end

        def on_tool_start(name, input_data, decision):
            send_event("tool_start", {"tool": name, "decision": decision})

        def on_tool_end(name, ok, output):
            send_event("tool_end", {"tool": name, "ok": ok, "output": output[:500]})

        self.agent.on_tool_start = on_tool_start
        self.agent.on_tool_end = on_tool_end

        try:
            send_event("start", {"message": msg})

            start = time.time()
            r = self.agent.think(msg)
            elapsed = time.time() - start

            send_event("response", {
                "text": r.text,
                "decision": r.decision,
                "risk": r.risk,
                "tool_calls": r.tool_calls_made,
                "turns": r.turns_used,
                "elapsed_ms": round(elapsed * 1000),
            })

            send_event("done", {})

        except Exception as e:
            send_event("error", {"error": str(e)})
        finally:
            self.agent.on_tool_start = original_tool_start
            self.agent.on_tool_end = original_tool_end


class ThreadedHTTPServer(HTTPServer):
    """HTTP server that handles requests in threads."""
    allow_reuse_address = True

    def process_request(self, request, client_address):
        t = threading.Thread(target=self.process_request_thread, args=(request, client_address))
        t.daemon = True
        t.start()

    def process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def run_server(host: str = "127.0.0.1", port: int = 8787, config_path: str = "helloagi.json"):
    """Start the HelloAGI API server."""
    settings = load_settings(config_path)
    agent = HelloAGIAgent(settings)

    HelloAGIHandler.agent = agent
    HelloAGIHandler.api_key = os.environ.get("HELLOAGI_API_KEY")

    srv = ThreadedHTTPServer((host, port), HelloAGIHandler)

    tools_count = len(agent.tool_registry.list_tools())
    skills_count = len(agent.skills.list_skills())
    llm_status = "connected" if agent._claude else "not configured"

    print(f"🧠 HelloAGI API v0.5.0")
    print(f"   Agent: {agent.identity.state.name} ({agent.identity.state.character})")
    print(f"   Tools: {tools_count} | Skills: {skills_count} | LLM: {llm_status} | SRG: active")
    print(f"   Listening: http://{host}:{port}")
    print(f"   Auth: {'API key required' if HelloAGIHandler.api_key else 'open (set HELLOAGI_API_KEY to secure)'}")
    print()
    print(f"   Endpoints:")
    print(f"     GET  /health       — Service health")
    print(f"     POST /chat         — Chat (JSON)")
    print(f"     POST /chat/stream  — Chat (SSE streaming)")
    print(f"     GET  /tools        — Available tools")
    print(f"     GET  /skills       — Learned skills")
    print(f"     GET  /identity     — Agent identity")
    print(f"     GET  /governance   — SRG config")
    print()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        srv.shutdown()
