# Deployment: keeping HelloAGI online

HelloAGI is a **Python** process (`python -m agi_runtime.cli serve …`). There is **no Node gateway** and **no pm2** in the core product—operators use an **OS-native supervisor** (recommended), **Docker**, or a **process manager** of their choice.

## 1. Recommended: OS background service

Same flow as [install.md](install.md#telegram-or-discord-after-onboarding):

```bash
helloagi service install --telegram
helloagi service start
helloagi service status
```

- **Linux (systemd user):** unit under `~/.config/systemd/user/helloagi.service` with `Restart=on-failure`, burst limits, and `PYTHONUNBUFFERED=1`. Reload after edits: `systemctl --user daemon-reload`.
- **macOS (launchd):** plist in `~/Library/LaunchAgents/` with `RunAtLoad` and `KeepAlive`.
- **Windows:** by default HelloAGI **does not** call Task Scheduler (`schtasks`) so non-admin installs avoid **Access is denied**. The service still installs `run-helloagi-service.cmd` under `%USERPROFILE%\.helloagi\service\`; use **`helloagi service start`** for a detached background process. For **auto-start at logon**, set **`HELLOAGI_SERVICE_NATIVE=1`**, open **Administrator** PowerShell, then **`helloagi service reinstall`**. Trigger is **`ONLOGON`** unless `HELLOAGI_WINDOWS_TASK_SCHEDULE=onstart` (machine boot; often requires elevation).

### After `pip install -U` or moving the venv

The unit records an **absolute** `python` path. If it drifts:

```bash
helloagi service doctor
helloagi service reinstall
helloagi service start
```

`reinstall` stops the service (best effort), rewrites the manifest, and re-registers the scheduler entry—similar in spirit to OpenClaw’s `openclaw gateway install --force` + restart.

## 2. Foreground / development

```bash
helloagi serve --telegram
```

Stops when the terminal closes; no OS registration.

## 3. Docker

See [install.md](install.md#option-e-docker) for `docker run` / image build. Suitable for homelab or CI; mount `.env` and config as volumes.

## 4. Optional: pm2, NSSM, tmux

Not required. Some operators wrap any long-running command:

- **pm2:** `pm2 start "helloagi serve --telegram" --name helloagi` (ensure cwd and env match production).
- **NSSM (Windows):** point NSSM at the same venv `python.exe` and arguments as `helloagi service install` would generate (`serve --host …`).
- **tmux/screen:** session persistence without systemd—fine for personal servers.

## 5. Comparison (mental model)

| Runtime | How it stays “active” |
|---------|------------------------|
| **HelloAGI** | `service install` + `service start` (systemd / launchd / schtasks) or Docker |
| **OpenClaw** | Long-lived **`openclaw gateway`** (Node); installer refreshes gateway service |
| **Hermes** | CLI + optional **`tui_gateway`**; often user-managed systemd |
| **Thoth** | **Desktop app** lifecycle; not a headless bot host by default |

Choose HelloAGI’s native service when you want **one stack** (Python only) and predictable units; use Docker when you want image-based rollouts.
