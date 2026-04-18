from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from typing import Any

import requests

from agi_runtime.config.env import save_env_values


@dataclass
class ServiceConfig:
    installed: bool = False
    host: str = "127.0.0.1"
    port: int = 8787
    config_path: str = "helloagi.json"
    policy_pack: str = "safe-default"
    telegram: bool = False
    discord: bool = False
    pid: int | None = None
    started_at: float | None = None


class ServiceManager:
    def __init__(self, state_path: str = "memory/service_state.json"):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> ServiceConfig:
        if not self.state_path.exists():
            return ServiceConfig()
        return ServiceConfig(**json.loads(self.state_path.read_text(encoding="utf-8")))

    def save(self, config: ServiceConfig):
        self.state_path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")

    def install(
        self,
        *,
        host: str,
        port: int,
        config_path: str,
        policy_pack: str,
        telegram: bool,
        discord: bool,
    ) -> ServiceConfig:
        cfg = self.load()
        cfg.installed = True
        cfg.host = host
        cfg.port = port
        cfg.config_path = config_path
        cfg.policy_pack = policy_pack
        cfg.telegram = telegram
        cfg.discord = discord
        self.save(cfg)
        self._ensure_service_token()
        return cfg

    def start(self) -> ServiceConfig:
        cfg = self.load()
        if not cfg.installed:
            raise RuntimeError("Service is not installed. Run `helloagi service install` first.")
        if cfg.pid and self._pid_alive(cfg.pid):
            return cfg

        cmd = [
            sys.executable,
            "-m",
            "agi_runtime.cli",
            "serve",
            "--host",
            cfg.host,
            "--port",
            str(cfg.port),
            "--config",
            cfg.config_path,
            "--policy",
            cfg.policy_pack,
        ]
        if cfg.telegram:
            cmd.append("--telegram")
        if cfg.discord:
            cmd.append("--discord")

        creationflags = 0
        kwargs: dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "cwd": os.getcwd(),
        }
        if os.name == "nt":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            kwargs["creationflags"] = creationflags
        else:
            kwargs["start_new_session"] = True

        proc = subprocess.Popen(cmd, **kwargs)
        cfg.pid = proc.pid
        cfg.started_at = time.time()
        self.save(cfg)
        return cfg

    def stop(self) -> ServiceConfig:
        cfg = self.load()
        if cfg.pid and self._pid_alive(cfg.pid):
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(cfg.pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(cfg.pid, signal.SIGTERM)
        cfg.pid = None
        cfg.started_at = None
        self.save(cfg)
        return cfg

    def uninstall(self) -> ServiceConfig:
        cfg = self.stop()
        cfg.installed = False
        self.save(cfg)
        return cfg

    def status(self) -> dict[str, Any]:
        cfg = self.load()
        running = bool(cfg.pid and self._pid_alive(cfg.pid))
        health = self.health() if running else {"ok": False, "error": "service not running"}
        return {
            "installed": cfg.installed,
            "running": running,
            "pid": cfg.pid,
            "host": cfg.host,
            "port": cfg.port,
            "policy_pack": cfg.policy_pack,
            "telegram": cfg.telegram,
            "discord": cfg.discord,
            "started_at": cfg.started_at,
            "health": health,
        }

    def health(self, timeout_s: float = 3.0) -> dict[str, Any]:
        cfg = self.load()
        token = os.environ.get("HELLOAGI_API_KEY", "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            response = requests.get(f"http://{cfg.host}:{cfg.port}/health", headers=headers, timeout=timeout_s)
            response.raise_for_status()
            return {"ok": True, "status_code": response.status_code, "data": response.json()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _ensure_service_token(self):
        if os.environ.get("HELLOAGI_API_KEY"):
            return
        token = secrets.token_urlsafe(24)
        save_env_values({"HELLOAGI_API_KEY": token})
        os.environ["HELLOAGI_API_KEY"] = token

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return str(pid) in result.stdout
            os.kill(pid, 0)
            return True
        except Exception:
            return False
