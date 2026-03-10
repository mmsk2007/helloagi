from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from agi_runtime.core.agent import HelloAGIAgent


class _Handler(BaseHTTPRequestHandler):
    agent = HelloAGIAgent()

    def _send_json(self, code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._send_json(200, {"ok": True, "service": "helloagi"})
        return self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/chat":
            return self._send_json(404, {"error": "not_found"})

        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n) if n > 0 else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._send_json(400, {"error": "invalid_json"})

        msg = data.get("message", "")
        r = self.agent.think(msg)
        return self._send_json(200, {
            "response": r.text,
            "decision": r.decision,
            "risk": r.risk,
        })


def run_server(host: str = "127.0.0.1", port: int = 8787):
    srv = HTTPServer((host, port), _Handler)
    print(f"HelloAGI API listening on http://{host}:{port}")
    srv.serve_forever()
