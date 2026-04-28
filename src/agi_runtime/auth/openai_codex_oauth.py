"""ChatGPT / Codex-style OpenAI OAuth (PKCE) for HelloAGI.

Uses the same public OAuth client id documented by the community ``openai-oauth``
project (override with ``HELLOAGI_OPENAI_OAUTH_CLIENT_ID``). This flow is
**unofficial**; you are responsible for complying with OpenAI terms.

Tokens live in ``memory/openai_codex_oauth.json`` (password-equivalent). Do not
commit or share that file.

If ``https://auth.openai.com`` returns **unknown_error** in the browser, the
community OAuth ``client_id`` + ``redirect_uri`` pair is often not accepted by
OpenAI. Use **official** ``codex login`` (OpenAI Codex CLI) once, then
``helloagi auth import-codex``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable

# Public client id from openai-oauth README (community); override via env.
DEFAULT_CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
DEFAULT_REDIRECT_PATH = "/auth/callback"
# Scopes commonly used for OpenAI account OAuth + refresh.
DEFAULT_SCOPE = "openid email profile offline_access"

_refresh_lock = threading.Lock()


def oauth_store_path() -> Path:
    return Path(os.environ.get("HELLOAGI_OPENAI_OAUTH_STORE", "memory/openai_codex_oauth.json"))


def _client_id() -> str:
    return (os.environ.get("HELLOAGI_OPENAI_OAUTH_CLIENT_ID") or DEFAULT_CODEX_OAUTH_CLIENT_ID).strip()


def _scope() -> str:
    return (os.environ.get("HELLOAGI_OPENAI_OAUTH_SCOPE") or DEFAULT_SCOPE).strip()


def _redirect_uri(port: int) -> str:
    host = (os.environ.get("HELLOAGI_OPENAI_OAUTH_BIND", "127.0.0.1") or "127.0.0.1").strip()
    return f"http://{host}:{port}{DEFAULT_REDIRECT_PATH}"


def default_codex_auth_json_path() -> Path:
    """Codex CLI default: ``$CODEX_HOME/auth.json`` or ``~/.codex/auth.json``."""
    home = os.environ.get("CODEX_HOME", "").strip()
    if home:
        return Path(home) / "auth.json"
    return Path.home() / ".codex" / "auth.json"


def _jwt_exp_unix(access_token: str) -> float | None:
    """Return JWT ``exp`` as Unix time, if the token looks like a JWT."""
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return None
        seg = parts[1]
        pad = "=" * (-len(seg) % 4)
        payload = json.loads(base64.urlsafe_b64decode(seg + pad))
        exp = payload.get("exp")
        return float(exp) if exp is not None else None
    except Exception:
        return None


def _extract_token_blob(data: dict[str, Any]) -> dict[str, Any]:
    t = data.get("tokens")
    if isinstance(t, dict):
        return t
    return data


def _pick_client_id(data: dict[str, Any], blob: dict[str, Any]) -> str:
    for d in (blob, data):
        for k in ("client_id", "oauth_client_id", "OAuthClientId"):
            v = d.get(k)
            if isinstance(v, str) and v.strip().startswith("app_"):
                return v.strip()
    return _client_id()


def _expires_at_from_blob(access_token: str, blob: dict[str, Any]) -> float:
    skew = 120.0
    if blob.get("expires_at") is not None:
        try:
            raw = float(blob["expires_at"])
            # Heuristic: ms vs s
            if raw > 1e12:
                raw = raw / 1000.0
            return raw - skew
        except (TypeError, ValueError):
            pass
    jwt_exp = _jwt_exp_unix(access_token)
    if jwt_exp:
        return jwt_exp - skew
    try:
        ei = int(blob.get("expires_in") or 0)
        if ei > 0:
            return time.time() + ei - skew
    except (TypeError, ValueError):
        pass
    return time.time() + 3600.0 - skew


def import_codex_auth_json(source: Path | None = None) -> LoginResult:
    """Copy tokens from the official Codex CLI ``auth.json`` into HelloAGI's store."""
    path = source or default_codex_auth_json_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"Codex auth file not found: {path}\n"
            "Install the official Codex CLI and run:  codex login\n"
            "Or pass an explicit file:  helloagi auth import-codex --path C:\\path\\to\\auth.json"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("auth.json must contain a JSON object")
    blob = _extract_token_blob(raw)
    access = blob.get("access_token") or raw.get("access_token")
    if not access or not isinstance(access, str):
        raise ValueError(
            f"No access_token in {path}. Open Codex CLI, run `codex login`, "
            "and ensure credentials are stored as a file (see OpenAI Codex docs: file-based auth)."
        )
    refresh = str(blob.get("refresh_token") or raw.get("refresh_token") or "")
    cid = _pick_client_id(raw, blob)
    exp_at = _expires_at_from_blob(access, blob if isinstance(blob, dict) else {})
    store = {
        "client_id": cid,
        "scope": raw.get("scope") or blob.get("scope") or DEFAULT_SCOPE,
        "access_token": access.strip(),
        "refresh_token": refresh.strip(),
        "expires_at": exp_at,
        "token_type": str(blob.get("token_type") or raw.get("token_type") or "Bearer"),
        "updated_at": time.time(),
        "imported_from": str(path.resolve()),
    }
    save_oauth_store(store)
    os.environ["OPENAI_AUTH_TOKEN"] = access.strip()
    return LoginResult(access_token=access.strip(), refresh_token=refresh.strip(), expires_at=exp_at)


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _http_form_post(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def load_oauth_store(path: Path | None = None) -> dict[str, Any] | None:
    p = path or oauth_store_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_oauth_store(data: dict[str, Any], path: Path | None = None) -> None:
    p = path or oauth_store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass


def refresh_tokens(refresh_token: str, client_id: str | None = None) -> dict[str, Any]:
    cid = client_id or _client_id()
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": cid,
    }
    try:
        return _http_form_post(TOKEN_URL, payload)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"Token refresh failed HTTP {e.code}: {err_body}") from e


def effective_access_token(
    *,
    path: Path | None = None,
    skew_sec: float = 120.0,
) -> str | None:
    """Return a valid access token, refreshing with refresh_token when near expiry."""
    p = path or oauth_store_path()
    with _refresh_lock:
        store = load_oauth_store(p)
        if not store or not store.get("access_token"):
            return None
        exp = float(store.get("expires_at") or 0.0)
        if time.time() < exp - skew_sec:
            return str(store["access_token"])

        rt = store.get("refresh_token")
        if not rt:
            return str(store["access_token"]) if store.get("access_token") else None

        data = refresh_tokens(str(rt), client_id=store.get("client_id") or _client_id())
        access = data.get("access_token")
        if not access:
            raise RuntimeError(f"Refresh response missing access_token: {list(data.keys())}")
        expires_in = int(data.get("expires_in") or 3600)
        store["access_token"] = access
        if data.get("refresh_token"):
            store["refresh_token"] = data["refresh_token"]
        store["expires_at"] = time.time() + max(60, expires_in) - skew_sec
        store["token_type"] = data.get("token_type", store.get("token_type", "Bearer"))
        store["updated_at"] = time.time()
        save_oauth_store(store, p)
        os.environ["OPENAI_AUTH_TOKEN"] = access
        return str(access)


def _parse_callback_url(url: str) -> tuple[str | None, str | None]:
    url = url.strip()
    if "code=" not in url and "error=" not in url:
        return None, None
    if "://" not in url:
        url = "http://dummy.local" + (url if url.startswith("/") else "/" + url)
    parsed = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(parsed.query)
    codes = q.get("code") or []
    states = q.get("state") or []
    code = codes[0] if codes else None
    state = states[0] if states else None
    return code, state


@dataclass
class LoginResult:
    access_token: str
    refresh_token: str
    expires_at: float


def exchange_code(code: str, redirect_uri: str, verifier: str, client_id: str | None = None) -> LoginResult:
    cid = client_id or _client_id()
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": cid,
        "code_verifier": verifier,
    }
    try:
        data = _http_form_post(TOKEN_URL, payload)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"Token exchange failed HTTP {e.code}: {err_body}") from e

    access = data.get("access_token")
    if not access:
        raise RuntimeError(f"Token response missing access_token: {data}")
    refresh = str(data.get("refresh_token") or "")
    expires_in = int(data.get("expires_in") or 3600)
    return LoginResult(
        access_token=str(access),
        refresh_token=refresh,
        expires_at=time.time() + max(60, expires_in) - 120.0,
    )


def _build_authorize_url(*, redirect_uri: str, state: str, challenge: str, client_id: str, scope: str) -> str:
    q = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTHORIZE_URL}?{q}"


def run_browser_oauth_login(
    *,
    port: int | None = None,
    bind: str | None = None,
    open_browser: bool = True,
    print_fn: Callable[[str], None] = print,
    input_fn: Callable[[str], str] = input,
) -> LoginResult:
    """Start localhost callback (or paste redirect URL), exchange code, return tokens."""
    start_port = port or int(os.environ.get("HELLOAGI_OPENAI_OAUTH_PORT", "1455"))
    if bind:
        os.environ["HELLOAGI_OPENAI_OAUTH_BIND"] = bind

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    client_id = _client_id()
    scope = _scope()

    chosen_port = start_port
    server: HTTPServer | None = None
    redirect_uri = ""
    for attempt in range(12):
        server = None
        try:
            redirect_uri = _redirect_uri(start_port + attempt)
            host_only = urllib.parse.urlparse(redirect_uri).hostname or "127.0.0.1"
            port_use = urllib.parse.urlparse(redirect_uri).port or (start_port + attempt)

            code_holder: dict[str, str | None] = {"code": None, "error": None, "got_state": None}

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, fmt: str, *args: Any) -> None:
                    return

                def do_GET(self) -> None:  # noqa: N802
                    if not self.path.startswith(DEFAULT_REDIRECT_PATH):
                        self.send_response(404)
                        self.end_headers()
                        return
                    qs = self.path.split("?", 1)[1] if "?" in self.path else ""
                    q = urllib.parse.parse_qs(qs)
                    if q.get("error"):
                        code_holder["error"] = (q.get("error_description") or q.get("error") or ["unknown"])[0]
                    codes = q.get("code") or []
                    states = q.get("state") or []
                    if codes:
                        code_holder["code"] = codes[0]
                        code_holder["got_state"] = states[0] if states else ""
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(
                        b"<html><body><h2>HelloAGI</h2><p>You can close this tab and return to the terminal.</p></body></html>"
                    )

            server = HTTPServer((host_only, port_use), Handler)
            chosen_port = port_use
            break
        except OSError:
            continue
    else:
        raise RuntimeError("Could not bind a localhost port for OAuth callback. Set HELLOAGI_OPENAI_OAUTH_PORT.")

    url = _build_authorize_url(
        redirect_uri=redirect_uri, state=state, challenge=challenge, client_id=client_id, scope=scope
    )

    print_fn("")
    print_fn("OpenAI ChatGPT / Codex OAuth (PKCE)")
    print_fn("-------------------------------------")
    print_fn(
        "If login fails with OpenAI **unknown_error**, use the official Codex CLI instead:\n"
        "  codex login\n"
        "then import:\n"
        "  helloagi auth import-codex\n"
        "(OpenAI only accepts certain OAuth client + redirect combinations.)\n"
    )
    print_fn(f"1. A browser will open (or open this URL yourself):\n\n   {url}\n")
    print_fn(
        "2. After you sign in, you will be redirected to localhost.\n"
        "   If the redirect fails (remote SSH, blocked port), copy the **full** redirect URL from the "
        "browser address bar and paste it below.\n"
    )

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            print_fn("(Could not open a browser automatically — use the URL above.)")

    code: str | None = None
    got_state: str | None = None

    if server:

        def serve() -> None:
            assert server is not None
            server.timeout = 0.5
            deadline = time.time() + 300.0
            while time.time() < deadline:
                server.handle_request()
                if code_holder["code"] or code_holder["error"]:
                    break

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        thread.join(timeout=300.0)
        if thread.is_alive():
            try:
                server.shutdown()
            except Exception:
                pass
        if code_holder["error"]:
            try:
                server.shutdown()
            except Exception:
                pass
            server.server_close()
            raise RuntimeError(f"OAuth error: {code_holder['error']}")
        code = code_holder["code"]
        got_state = code_holder.get("got_state") if code_holder["code"] else None
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass

    if not code:
        print_fn("No callback received on localhost. Paste the full redirect URL now (or Enter to abort):")
        pasted = input_fn("URL: ").strip()
        if not pasted:
            raise RuntimeError("Aborted: no authorization code.")
        code, pasted_state = _parse_callback_url(pasted)
        got_state = pasted_state
        if not code:
            raise RuntimeError("Could not parse ?code= from the pasted URL.")

    if got_state and got_state != state:
        raise RuntimeError("OAuth state mismatch — refusing to exchange code (possible CSRF).")

    result = exchange_code(code, redirect_uri, verifier, client_id=client_id)
    store = {
        "client_id": client_id,
        "scope": scope,
        "access_token": result.access_token,
        "refresh_token": result.refresh_token,
        "expires_at": result.expires_at,
        "token_type": "Bearer",
        "updated_at": time.time(),
    }
    save_oauth_store(store)
    os.environ["OPENAI_AUTH_TOKEN"] = result.access_token
    print_fn("")
    print_fn(f"Saved OAuth tokens to {oauth_store_path()}")
    print_fn("OPENAI_AUTH_TOKEN is set in this process for immediate use; add nothing to .env unless you want a static key too.")
    return result
