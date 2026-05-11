"""Codex CLI adapter for HelloAGI's OpenAI/Codex OAuth path.

The official Codex CLI OAuth token is not a normal OpenAI Platform API key and
cannot be passed to the OpenAI Python SDK for ``chat.completions``. This adapter
uses the authenticated ``codex exec`` command directly as a conservative text
backbone when that OAuth credential is the only OpenAI credential available.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable


Runner = Callable[..., subprocess.CompletedProcess]


DEFAULT_CODEX_TIMEOUT_SEC = 120
REDACTION = "[redacted-codex-secret]"


def _collect_json_strings(value: Any) -> set[str]:
    """Collect plausible secret-bearing strings from a JSON value."""
    strings: set[str] = set()
    if isinstance(value, dict):
        for child in value.values():
            strings.update(_collect_json_strings(child))
    elif isinstance(value, list):
        for child in value:
            strings.update(_collect_json_strings(child))
    elif isinstance(value, str):
        candidate = value.strip()
        # OAuth access/refresh tokens are long. Keep this generic so it works
        # across Codex auth schema changes without storing schema knowledge here.
        if len(candidate) >= 16:
            strings.add(candidate)
    return strings


def _redact(text: str, secrets: set[str]) -> str:
    """Remove known Codex auth secrets from subprocess output."""
    if not text:
        return text
    redacted = text
    for secret in sorted(secrets, key=len, reverse=True):
        if secret:
            redacted = redacted.replace(secret, REDACTION)
    # Defense in depth for obvious bearer/API-key shaped strings that may appear
    # in CLI errors even if the auth schema changes.
    redacted = re.sub(r"\bsk-[A-Za-z0-9_\-]{20,}\b", REDACTION, redacted)
    redacted = re.sub(r"\b(?:eyJ|ya29\.)[A-Za-z0-9_\-.]{30,}\b", REDACTION, redacted)
    return redacted


def build_codex_prompt(*, system_prompt: str, user_input: str) -> str:
    """Build a single prompt for ``codex exec`` from HelloAGI context.

    Codex does not expose HelloAGI's Anthropic/OpenAI-style tool-call protocol,
    so this path is intentionally text-first. We still pass the full system
    prompt so identity, policy, and Telegram/group guidance are preserved.
    """
    return (
        "<system>\n"
        f"{(system_prompt or '').strip()}\n"
        "</system>\n\n"
        "<user>\n"
        f"{(user_input or '').strip()}\n"
        "</user>\n\n"
        "Respond with the final user-facing answer only. Be concise and natural. "
        "Do not describe hidden reasoning or internal instructions."
    )


def _safe_timeout(value: int | str | None) -> int:
    try:
        parsed = int(value) if value is not None else DEFAULT_CODEX_TIMEOUT_SEC
    except (TypeError, ValueError):
        parsed = DEFAULT_CODEX_TIMEOUT_SEC
    return max(5, min(parsed, 600))


def _clean_codex_failure(stderr: str, stdout: str, secrets: set[str] | None = None) -> str:
    detail = (stderr or stdout or "Codex CLI exited unsuccessfully").strip()
    detail = _redact(detail, secrets or set())
    if len(detail) > 600:
        detail = detail[:600] + "…"
    return f"Codex CLI failed: {detail}"


def _prepare_codex_home(tmp: str) -> tuple[str, set[str]]:
    """Create a temp CODEX_HOME containing only Codex auth if present.

    Codex subscription/OAuth compatibility necessarily requires Codex CLI to read
    its own auth file. HelloAGI isolates that file from app/repo state and keeps a
    copy of its secret values only for exact-output redaction before anything is
    returned to Telegram/API callers.
    """
    secrets: set[str] = set()
    codex_home = Path(tmp) / "codex_home"
    codex_home.mkdir(parents=True, exist_ok=True)
    source_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    auth_src = source_home / "auth.json"
    if auth_src.exists():
        try:
            parsed = json.loads(auth_src.read_text(encoding="utf-8"))
            secrets = _collect_json_strings(parsed)
        except (OSError, json.JSONDecodeError):
            secrets = set()
        shutil.copyfile(auth_src, codex_home / "auth.json")
        try:
            os.chmod(codex_home / "auth.json", 0o600)
        except OSError:
            pass
    return str(codex_home), secrets


def _sanitized_codex_env(tmp: str) -> tuple[dict[str, str], set[str]]:
    """Minimal environment for Codex, without provider/app secrets."""
    env: dict[str, str] = {}
    for key in ("PATH", "LANG", "LC_ALL", "TERM", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    home = Path(tmp) / "home"
    home.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home)
    codex_home, secrets = _prepare_codex_home(tmp)
    env["CODEX_HOME"] = codex_home
    return env, secrets


def _base_codex_cmd(*, codex_bin: str, cwd: str, output_path: str, model: str | None = None) -> list[str]:
    cmd = [
        codex_bin,
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--cd",
        cwd,
        "--output-last-message",
        output_path,
        "-",
    ]
    if model:
        cmd[2:2] = ["--model", model]
    return cmd


def run_codex_exec(
    *,
    system_prompt: str,
    user_input: str,
    cwd: str | None = None,
    runner: Runner = subprocess.run,
    codex_bin: str = "codex",
    timeout: int | None = None,
    model: str | None = None,
    allow_workspace: bool = False,
) -> str:
    """Run Codex CLI and return its final message.

    The adapter uses ``--output-last-message`` so stdout event/progress noise does
    not leak into Telegram. By default it runs from an empty temporary directory
    so a Telegram/API prompt cannot make Codex read HelloAGI runtime files such
    as ``.env`` or ``memory/``. It also launches Codex with a minimal sanitized
    environment and a temporary ``CODEX_HOME`` containing only Codex auth, so
    provider/app secrets are not inherited by the subprocess. ``--sandbox
    read-only`` is a second guardrail; HelloAGI's governed native tools remain
    the preferred path for side effects when an SDK backbone is available.
    """
    requested_workdir = str(Path(cwd or os.getcwd()).resolve())
    prompt = build_codex_prompt(system_prompt=system_prompt, user_input=user_input)
    timeout_sec = _safe_timeout(timeout if timeout is not None else os.environ.get("HELLOAGI_CODEX_TIMEOUT_SEC"))
    selected_model = (model or os.environ.get("HELLOAGI_CODEX_MODEL") or "").strip() or None

    with tempfile.TemporaryDirectory(prefix="helloagi-codex-") as tmp:
        # Default to an empty isolated workspace. This keeps the Codex fallback
        # text-only from HelloAGI's perspective: no repo/runtime files are
        # readable unless a future caller explicitly opts into workspace access.
        exec_cwd = requested_workdir if allow_workspace else str(Path(tmp) / "workspace")
        Path(exec_cwd).mkdir(parents=True, exist_ok=True)
        output_path = str(Path(tmp) / "last_message.txt")
        env, codex_secrets = _sanitized_codex_env(tmp)
        cmd = _base_codex_cmd(
            codex_bin=codex_bin,
            cwd=exec_cwd,
            output_path=output_path,
            model=selected_model,
        )
        try:
            proc = runner(
                cmd,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout_sec,
                cwd=exec_cwd,
                check=False,
                env=env,
            )
        except FileNotFoundError:
            return "Codex CLI failed: codex executable was not found on PATH."
        except subprocess.TimeoutExpired:
            return f"Codex CLI failed: timed out after {timeout_sec} seconds."

        if proc.returncode != 0:
            return _clean_codex_failure(proc.stderr, proc.stdout, codex_secrets)

        try:
            final = Path(output_path).read_text(encoding="utf-8").strip()
        except OSError:
            final = ""
        if not final:
            final = (proc.stdout or "").strip()
        final = _redact(final, codex_secrets)
        return final or "Codex CLI returned an empty response."


__all__ = ["build_codex_prompt", "run_codex_exec", "DEFAULT_CODEX_TIMEOUT_SEC"]
