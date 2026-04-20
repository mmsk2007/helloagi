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

from agi_runtime.channels.voice_presence import voice_presence_store
from agi_runtime.config.env import resolve_env_value
from agi_runtime.core.agent import HelloAGIAgent
from agi_runtime.config.settings import RuntimeSettings, load_settings


class HelloAGIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the HelloAGI API."""

    agent: HelloAGIAgent = None
    api_key: str = None
    auth_required: bool = False
    auth_env_key: str = "HELLOAGI_API_KEY"
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
        if self.headers.get("X-API-Key", "") == self.api_key:
            return True
        query = parse_qs(urlparse(self.path).query)
        for key in ("api_key", "token"):
            values = query.get(key, [])
            if values and values[0] == self.api_key:
                return True
        return False

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
        elif path == "/voice/state":
            return self._handle_voice_state()
        elif path == "/voice/events":
            return self._handle_voice_events()
        elif path == "/voice/monitor":
            return self._handle_voice_monitor()
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
        tools = self.agent._list_allowed_tools()
        voice_state = voice_presence_store().snapshot()
        self._send_json(200, {
            "ok": True,
            "service": "helloagi",
            "version": "0.5.0",
            "agent": self.agent.identity.state.name,
            "policy_pack": self.agent.policy_pack.name,
            "tools": len(tools),
            "skills": len(self.agent.skills.list_skills()),
            "llm_configured": self.agent._claude is not None,
            "srg_active": True,
            "auth_required": self.auth_required,
            "auth_mode": "token" if self.auth_required else "none",
            "auth_env_key": self.auth_env_key,
            "uptime_seconds": round(uptime),
            "total_requests": self._stats["requests"],
            "voice": {
                "state": voice_state["state"],
                "active": voice_state["active"],
                "wake_word": voice_state["wake_word"],
                "updated_at": voice_state["updated_at"],
            },
        })

    def _handle_voice_state(self):
        self._send_json(200, {"voice": voice_presence_store().snapshot()})

    def _handle_voice_monitor(self):
        body = _voice_monitor_html(auth_required=self.auth_required).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _handle_voice_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        store = voice_presence_store()
        snapshot = store.snapshot()
        version = int(snapshot.get("version", 0))

        def send(event_type: str, payload: dict):
            body = json.dumps(payload, ensure_ascii=False)
            self.wfile.write(f"event: {event_type}\ndata: {body}\n\n".encode("utf-8"))
            self.wfile.flush()

        try:
            send("voice", snapshot)
            while True:
                changed = store.wait_for_change(version, timeout=15.0)
                if changed is None:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                version = int(changed.get("version", version))
                send("voice", changed)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _handle_tools(self):
        tools = self.agent._list_allowed_tools()
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
            "policy_pack": self.agent.policy_pack.name,
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
        principal_id = str(
            data.get("principal_id")
            or data.get("session_id")
            or f"api:{self.client_address[0]}"
        )
        self.agent.set_principal(principal_id)

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
        principal_id = str(
            data.get("principal_id")
            or data.get("session_id")
            or f"api:{self.client_address[0]}"
        )
        self.agent.set_principal(principal_id)

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


def run_server(
    host: str = "127.0.0.1",
    port: int = 8787,
    config_path: str = "helloagi.json",
    policy_pack: str = "safe-default",
    require_auth: bool = False,
):
    """Start the HelloAGI API server."""
    settings = load_settings(config_path)
    agent = HelloAGIAgent(settings, policy_pack=policy_pack)
    api_key = resolve_env_value("HELLOAGI_API_KEY")
    if require_auth and not api_key:
        raise RuntimeError("HELLOAGI_API_KEY is required when --require-auth is enabled.")

    HelloAGIHandler.agent = agent
    HelloAGIHandler.api_key = api_key if (require_auth or api_key) else None
    HelloAGIHandler.auth_required = bool(require_auth or api_key)
    HelloAGIHandler.auth_env_key = "HELLOAGI_API_KEY"

    srv = ThreadedHTTPServer((host, port), HelloAGIHandler)

    tools_count = len(agent._list_allowed_tools())
    skills_count = len(agent.skills.list_skills())
    llm_status = "connected" if agent._claude else "not configured"

    print(f"🧠 HelloAGI API v0.5.0")
    print(f"   Agent: {agent.identity.state.name} ({agent.identity.state.character})")
    print(f"   Tools: {tools_count} | Skills: {skills_count} | LLM: {llm_status} | SRG: active")
    print(f"   Listening: http://{host}:{port}")
    print(f"   Auth: {'API key required' if HelloAGIHandler.auth_required else 'open (set HELLOAGI_API_KEY or use --require-auth to secure)'}")
    print()
    print(f"   Endpoints:")
    print(f"     GET  /health       — Service health")
    print(f"     POST /chat         — Chat (JSON)")
    print(f"     POST /chat/stream  — Chat (SSE streaming)")
    print(f"     GET  /voice/state  — Voice status JSON")
    print(f"     GET  /voice/events — Voice status SSE")
    print(f"     GET  /voice/monitor — Browser voice monitor")
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


def _voice_monitor_html(*, auth_required: bool) -> str:
    auth_note = (
        "This server requires auth. Open this page with ?api_key=YOUR_TOKEN if needed."
        if auth_required
        else "No auth token required on this server."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HelloAGI Voice Monitor</title>
  <style>
    :root {{
      --bg: #0d1b1e;
      --panel: #13262b;
      --text: #e8f1ee;
      --muted: #8ea8a2;
      --idle: #5f7d77;
      --listening: #31c48d;
      --thinking: #f59e0b;
      --speaking: #38bdf8;
      --error: #f87171;
      --approval: #f97316;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at top, rgba(56,189,248,0.18), transparent 32%),
        radial-gradient(circle at bottom, rgba(49,196,141,0.16), transparent 28%),
        var(--bg);
      color: var(--text);
      font: 16px/1.5 "Segoe UI", system-ui, sans-serif;
      padding: 24px;
    }}
    .panel {{
      width: min(780px, 100%);
      background: rgba(19, 38, 43, 0.88);
      border: 1px solid rgba(232,241,238,0.10);
      border-radius: 24px;
      padding: 28px;
      box-shadow: 0 30px 80px rgba(0,0,0,0.35);
      backdrop-filter: blur(18px);
    }}
    .eyebrow {{
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 12px;
      margin-bottom: 8px;
    }}
    h1 {{
      margin: 0 0 18px;
      font-size: clamp(28px, 5vw, 48px);
      line-height: 1;
    }}
    .orb-wrap {{
      display: grid;
      place-items: center;
      margin: 22px 0 28px;
    }}
    .orb {{
      width: 168px;
      aspect-ratio: 1;
      border-radius: 50%;
      background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.35), transparent 35%), var(--idle);
      box-shadow: 0 0 0 0 rgba(95,125,119,0.35);
      transition: background 180ms ease, transform 180ms ease, box-shadow 180ms ease;
    }}
    .orb.listening {{
      background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.48), transparent 35%), var(--listening);
      animation: pulse 1.2s infinite;
    }}
    .orb.transcribing, .orb.thinking {{
      background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.48), transparent 35%), var(--thinking);
      animation: pulse 1.0s infinite;
    }}
    .orb.speaking {{
      background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.52), transparent 35%), var(--speaking);
      animation: pulse 0.8s infinite;
      transform: scale(1.04);
    }}
    .orb.approval {{
      background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.52), transparent 35%), var(--approval);
      animation: pulse 1.0s infinite;
    }}
    .orb.error {{
      background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.42), transparent 35%), var(--error);
      box-shadow: 0 0 0 12px rgba(248,113,113,0.12);
    }}
    @keyframes pulse {{
      0% {{ box-shadow: 0 0 0 0 rgba(255,255,255,0.18); }}
      70% {{ box-shadow: 0 0 0 28px rgba(255,255,255,0); }}
      100% {{ box-shadow: 0 0 0 0 rgba(255,255,255,0); }}
    }}
    .status {{
      font-size: 24px;
      font-weight: 700;
      margin: 0 0 6px;
      text-transform: capitalize;
    }}
    .detail {{
      margin: 0 0 18px;
      color: var(--muted);
      min-height: 24px;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .card {{
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 16px;
      padding: 14px;
    }}
    .label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 6px;
    }}
    .value {{
      font-size: 16px;
      word-break: break-word;
    }}
    .foot {{
      color: var(--muted);
      font-size: 13px;
      margin-top: 18px;
    }}
  </style>
</head>
<body>
  <main class="panel">
    <div class="eyebrow">HelloAGI Local Voice</div>
    <h1>Voice Monitor</h1>
    <div class="orb-wrap"><div id="orb" class="orb"></div></div>
    <div class="status" id="status">Inactive</div>
    <p class="detail" id="detail">Waiting for voice activity.</p>
    <section class="meta">
      <div class="card"><span class="label">Wake Word</span><div class="value" id="wakeWord">lana</div></div>
      <div class="card"><span class="label">Last Heard</span><div class="value" id="lastHeard">—</div></div>
      <div class="card"><span class="label">Last Spoken</span><div class="value" id="lastSpoken">—</div></div>
      <div class="card"><span class="label">Updated</span><div class="value" id="updatedAt">—</div></div>
    </section>
    <p class="foot">{auth_note}</p>
  </main>
  <script>
    const qs = new URLSearchParams(window.location.search);
    const suffix = qs.toString() ? `?${{qs.toString()}}` : "";
    const orb = document.getElementById("orb");
    const statusEl = document.getElementById("status");
    const detailEl = document.getElementById("detail");
    const wakeWordEl = document.getElementById("wakeWord");
    const lastHeardEl = document.getElementById("lastHeard");
    const lastSpokenEl = document.getElementById("lastSpoken");
    const updatedAtEl = document.getElementById("updatedAt");

    function formatTime(ts) {{
      if (!ts) return "—";
      return new Date(ts * 1000).toLocaleTimeString();
    }}

    function render(payload) {{
      const state = (payload.state || "inactive").toLowerCase();
      orb.className = `orb ${{state}}`;
      statusEl.textContent = state;
      detailEl.textContent = payload.detail || "Waiting for voice activity.";
      wakeWordEl.textContent = payload.wake_word || "lana";
      lastHeardEl.textContent = payload.last_heard || "—";
      lastSpokenEl.textContent = payload.last_spoken || "—";
      updatedAtEl.textContent = formatTime(payload.updated_at);
    }}

    fetch(`/voice/state${{suffix}}`)
      .then((r) => r.json())
      .then((data) => render(data.voice || {{}}))
      .catch(() => {{}});

    const source = new EventSource(`/voice/events${{suffix}}`);
    source.addEventListener("voice", (event) => {{
      render(JSON.parse(event.data));
    }});
    source.onerror = () => {{
      detailEl.textContent = "Waiting for voice event stream...";
    }};
  </script>
</body>
</html>"""
