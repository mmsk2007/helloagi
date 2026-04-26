from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import os
import platform
import secrets
import shlex
import signal
import subprocess
import sys
import time
from typing import Any

import requests

from agi_runtime.config.env import resolve_env_value, save_env_values


@dataclass
class ServiceConfig:
    installed: bool = False
    host: str = "127.0.0.1"
    port: int = 8787
    config_path: str = "helloagi.json"
    workdir: str = ""
    policy_pack: str = "safe-default"
    telegram: bool = False
    discord: bool = False
    enabled_extensions: list[str] = field(default_factory=list)
    backend: str = "process"
    service_name: str = "helloagi"
    manifest_path: str = ""
    native_registered: bool = False
    last_error: str = ""
    auth_required: bool = False
    auth_env_key: str = "HELLOAGI_API_KEY"
    pid: int | None = None
    started_at: float | None = None


class ServiceManager:
    def __init__(
        self,
        state_path: str = "memory/service_state.json",
        *,
        install_root: str | None = None,
        platform_name: str | None = None,
        native_control: bool = True,
    ):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.platform_name = (platform_name or platform.system()).lower()
        self.install_root = Path(install_root) if install_root else self._default_install_root()
        try:
            self.install_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.native_control = native_control

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
        enabled_extensions: list[str] | None = None,
        workdir: str | None = None,
        require_auth: bool = True,
        auth_env_key: str = "HELLOAGI_API_KEY",
    ) -> ServiceConfig:
        cfg = self.load()
        cfg.installed = True
        cfg.host = host
        cfg.port = port
        cfg.config_path = config_path
        cfg.workdir = str(Path(workdir or os.getcwd()).resolve())
        cfg.policy_pack = policy_pack
        merged_extensions = set(enabled_extensions or [])
        if telegram:
            merged_extensions.add("telegram")
        if discord:
            merged_extensions.add("discord")
        cfg.enabled_extensions = sorted(merged_extensions)
        cfg.telegram = "telegram" in cfg.enabled_extensions
        cfg.discord = "discord" in cfg.enabled_extensions
        cfg.backend = self._detect_backend()
        cfg.service_name = self._service_name()
        cfg.manifest_path = str(self._manifest_path(cfg))
        cfg.auth_required = require_auth
        cfg.auth_env_key = auth_env_key
        cfg.last_error = ""
        self._ensure_service_token(cfg.auth_env_key) if cfg.auth_required else None
        self._write_manifest(cfg)
        cfg.native_registered = self._register_native_service(cfg)
        self.save(cfg)
        return cfg

    def start(self) -> ServiceConfig:
        cfg = self.load()
        if not cfg.installed:
            raise RuntimeError("Service is not installed. Run `helloagi service install` first.")
        if cfg.auth_required and not resolve_env_value(cfg.auth_env_key):
            raise RuntimeError(f"Missing required service auth token in {cfg.auth_env_key}.")
        if self._is_running(cfg):
            return cfg

        if cfg.native_registered:
            try:
                self._native_start(cfg)
                cfg.started_at = time.time()
                cfg.last_error = ""
                self.save(cfg)
                return cfg
            except Exception as exc:
                cfg.last_error = f"native start failed: {exc}"

        proc = self._spawn_process(cfg)
        cfg.pid = proc.pid
        cfg.started_at = time.time()
        self.save(cfg)
        return cfg

    def stop(self) -> ServiceConfig:
        cfg = self.load()
        native_error = ""
        if cfg.native_registered:
            try:
                self._native_stop(cfg)
            except Exception as exc:
                native_error = str(exc)
        if cfg.pid and self._pid_alive(cfg.pid):
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(cfg.pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(cfg.pid, signal.SIGTERM)
        cfg.pid = None
        cfg.started_at = None
        cfg.last_error = native_error
        self.save(cfg)
        return cfg

    def uninstall(self) -> ServiceConfig:
        cfg = self.stop()
        if cfg.native_registered:
            try:
                self._native_uninstall(cfg)
            except Exception as exc:
                cfg.last_error = f"native uninstall failed: {exc}"
        manifest_path = Path(cfg.manifest_path) if cfg.manifest_path else None
        if manifest_path and manifest_path.exists():
            manifest_path.unlink(missing_ok=True)
        cfg.installed = False
        cfg.native_registered = False
        self.save(cfg)
        return cfg

    def status(self) -> dict[str, Any]:
        cfg = self.load()
        running = self._is_running(cfg)
        health = self.health() if running else {"ok": False, "error": "service not running"}
        return {
            "installed": cfg.installed,
            "running": running,
            "backend": cfg.backend,
            "service_name": cfg.service_name,
            "manifest_path": cfg.manifest_path,
            "native_registered": cfg.native_registered,
            "pid": cfg.pid,
            "host": cfg.host,
            "port": cfg.port,
            "workdir": cfg.workdir,
            "policy_pack": cfg.policy_pack,
            "enabled_extensions": cfg.enabled_extensions,
            "telegram": cfg.telegram,
            "discord": cfg.discord,
            "auth_required": cfg.auth_required,
            "auth_env_key": cfg.auth_env_key,
            "auth_configured": bool(resolve_env_value(cfg.auth_env_key)),
            "started_at": cfg.started_at,
            "last_error": cfg.last_error,
            "health": health,
        }

    def health(self, timeout_s: float = 3.0) -> dict[str, Any]:
        cfg = self.load()
        token = resolve_env_value(cfg.auth_env_key or "HELLOAGI_API_KEY")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            response = requests.get(f"http://{cfg.host}:{cfg.port}/health", headers=headers, timeout=timeout_s)
            response.raise_for_status()
            return {"ok": True, "status_code": response.status_code, "data": response.json()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _default_install_root(self) -> Path:
        if self.platform_name.startswith("darwin"):
            return Path.home() / "Library" / "LaunchAgents"
        if self.platform_name.startswith("windows"):
            return Path.home() / ".helloagi" / "service"
        return Path.home() / ".config" / "systemd" / "user"

    def _detect_backend(self) -> str:
        if self.platform_name.startswith("darwin"):
            return "launchd"
        if self.platform_name.startswith("windows"):
            return "windows-task"
        return "systemd-user"

    def _service_name(self) -> str:
        if self._detect_backend() == "launchd":
            return "com.helloagi.agent"
        return "helloagi"

    def _service_command(self, cfg: ServiceConfig) -> list[str]:
        # Resolved absolute interpreter so launchd/systemd/schtasks work when the unit
        # runs outside the user's shell (venv PATH not required).
        python_exe = str(Path(sys.executable).resolve())
        command = [
            python_exe,
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
        for name in cfg.enabled_extensions:
            command.extend(["--extension", name])
        if cfg.auth_required:
            command.append("--require-auth")
        return command

    def _manifest_path(self, cfg: ServiceConfig) -> Path:
        if cfg.backend == "launchd":
            return self.install_root / f"{cfg.service_name}.plist"
        if cfg.backend == "windows-task":
            return self.install_root / "run-helloagi-service.cmd"
        return self.install_root / f"{cfg.service_name}.service"

    def _write_manifest(self, cfg: ServiceConfig):
        manifest_path = self._manifest_path(cfg)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        command = self._service_command(cfg)

        if cfg.backend == "windows-task":
            lines = [
                "@echo off",
                f'cd /d "{cfg.workdir}"',
                subprocess.list2cmdline(command),
            ]
            manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return

        if cfg.backend == "launchd":
            program_args = "\n".join(f"      <string>{arg}</string>" for arg in command)
            plist = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                "<plist version=\"1.0\">\n"
                "  <dict>\n"
                f"    <key>Label</key><string>{cfg.service_name}</string>\n"
                "    <key>ProgramArguments</key>\n"
                "    <array>\n"
                f"{program_args}\n"
                "    </array>\n"
                f"    <key>WorkingDirectory</key><string>{cfg.workdir}</string>\n"
                "    <key>RunAtLoad</key><true/>\n"
                "    <key>KeepAlive</key><true/>\n"
                "  </dict>\n"
                "</plist>\n"
            )
            manifest_path.write_text(plist, encoding="utf-8")
            return

        command_text = shlex.join(command)
        unit = (
            "[Unit]\n"
            "Description=HelloAGI local service\n"
            "After=network.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={cfg.workdir}\n"
            f"ExecStart={command_text}\n"
            "Restart=on-failure\n"
            "RestartSec=3\n\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )
        manifest_path.write_text(unit, encoding="utf-8")

    def _register_native_service(self, cfg: ServiceConfig) -> bool:
        manifest_path = Path(cfg.manifest_path)
        try:
            if not self.native_control:
                return False
            if cfg.backend == "windows-task":
                subprocess.run(
                    [
                        "schtasks",
                        "/Create",
                        "/F",
                        "/SC",
                        "ONLOGON",
                        "/TN",
                        cfg.service_name,
                        "/TR",
                        str(manifest_path),
                    ],
                    capture_output=True,
                    check=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                return True
            if cfg.backend == "launchd":
                uid = str(os.getuid())
                subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(manifest_path)], capture_output=True, check=True, text=True)
                return True
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=True, text=True)
            subprocess.run(["systemctl", "--user", "enable", cfg.service_name], capture_output=True, check=True, text=True)
            return True
        except Exception as exc:
            cfg.last_error = f"native registration failed: {exc}"
            return False

    def _native_start(self, cfg: ServiceConfig):
        if not self.native_control:
            raise RuntimeError("native control disabled")
        if cfg.backend == "windows-task":
            subprocess.run(["schtasks", "/Run", "/TN", cfg.service_name], capture_output=True, check=True, text=True)
            return
        if cfg.backend == "launchd":
            subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{cfg.service_name}"], capture_output=True, check=True, text=True)
            return
        subprocess.run(["systemctl", "--user", "start", cfg.service_name], capture_output=True, check=True, text=True)

    def _native_stop(self, cfg: ServiceConfig):
        if not self.native_control:
            raise RuntimeError("native control disabled")
        if cfg.backend == "windows-task":
            subprocess.run(["schtasks", "/End", "/TN", cfg.service_name], capture_output=True, check=True, text=True)
            return
        if cfg.backend == "launchd":
            subprocess.run(["launchctl", "stop", cfg.service_name], capture_output=True, check=True, text=True)
            return
        subprocess.run(["systemctl", "--user", "stop", cfg.service_name], capture_output=True, check=True, text=True)

    def _native_uninstall(self, cfg: ServiceConfig):
        if not self.native_control:
            raise RuntimeError("native control disabled")
        if cfg.backend == "windows-task":
            subprocess.run(["schtasks", "/Delete", "/TN", cfg.service_name, "/F"], capture_output=True, check=True, text=True)
            return
        if cfg.backend == "launchd":
            subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(Path(cfg.manifest_path))], capture_output=True, check=True, text=True)
            return
        subprocess.run(["systemctl", "--user", "disable", cfg.service_name], capture_output=True, check=True, text=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=True, text=True)

    def _spawn_process(self, cfg: ServiceConfig):
        creationflags = 0
        kwargs: dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "cwd": cfg.workdir or os.getcwd(),
        }
        if os.name == "nt":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            kwargs["creationflags"] = creationflags
        else:
            kwargs["start_new_session"] = True
        return subprocess.Popen(self._service_command(cfg), **kwargs)

    def _is_running(self, cfg: ServiceConfig) -> bool:
        if cfg.native_registered and self._native_running(cfg):
            return True
        return bool(cfg.pid and self._pid_alive(cfg.pid))

    def _native_running(self, cfg: ServiceConfig) -> bool:
        if not self.native_control:
            return False
        try:
            if cfg.backend == "windows-task":
                result = subprocess.run(
                    ["schtasks", "/Query", "/TN", cfg.service_name, "/FO", "LIST", "/V"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                return "Running" in result.stdout
            if cfg.backend == "launchd":
                result = subprocess.run(
                    ["launchctl", "print", f"gui/{os.getuid()}/{cfg.service_name}"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return result.returncode == 0
            result = subprocess.run(
                ["systemctl", "--user", "is-active", cfg.service_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() == "active"
        except Exception:
            return False

    def _ensure_service_token(self, env_key: str = "HELLOAGI_API_KEY"):
        if resolve_env_value(env_key):
            return
        token = secrets.token_urlsafe(24)
        save_env_values({env_key: token})
        os.environ[env_key] = token

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                )
                return str(pid) in result.stdout
            os.kill(pid, 0)
            return True
        except Exception:
            return False
