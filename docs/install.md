# Install & Setup Guide

## Requirements

- **Python 3.9+** (3.11 recommended)
- **pip** (comes with Python)
- **Anthropic API key** (optional — needed for Claude backbone, not required for local-only mode)

## Quick path (recommended order)

1. Create and activate a **venv** (see Option 0 below), especially on Windows or conda `base`.
2. **Install** HelloAGI: `pip install -e ".[rich,telegram]"` from a clone, or `pip install "helloagi[rich,telegram]"` from PyPI.
3. **Onboard:** `helloagi onboard` or `python -m agi_runtime.cli onboard` (same interpreter as step 2).
4. **Verify:** `helloagi health` and `helloagi onboard-status`.

There is no separate OpenClaw-style `doctor --fix` auto-migration yet; if config drifts, re-run `helloagi onboard` or edit `helloagi.json` / `.env` manually.

---

## Option 0: Virtual environment (recommended on Windows / conda)

Installing into **Anaconda/Miniconda `base`** often breaks with partial uninstalls (folders like `~atplotlib`, missing `*.dist-info`, or **`WinError 183`** during upgrades). Use a **dedicated venv** for HelloAGI:

**Windows (PowerShell):**

```powershell
cd helloagi
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[rich,telegram]"
```

If `Activate.ps1` is blocked, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

**macOS / Linux:**

```bash
cd helloagi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[rich,telegram]"
```

Then run `helloagi onboard` and all other commands **with this venv activated**. Editable install **must** include the project path: `pip install -e .` (the `.` is required).

---

## Option A: One-Liner Install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.sh | bash
```

The installer installs `helloagi[rich,telegram]`, initializes the runtime, runs a health check, and launches the onboarding wizard immediately.

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.ps1 | iex
```

This follows the same flow on Windows and launches onboarding without requiring the `helloagi` console script to be on PATH yet.

## Option B: PyPI Install

Prefer a **venv** (Option 0) over `--user` into conda `base` on Windows.

```bash
python -m pip install "helloagi[rich,telegram]"
python -m agi_runtime.cli onboard
```

This works even before shell PATH refreshes expose the `helloagi` command (after install, `agi_runtime` is importable in that same interpreter).

## Option B2: Tool-style install

```bash
pipx install helloagi
# or
uv tool install helloagi
```

Then run:

```bash
helloagi onboard
helloagi health
```

For channel extras, install with extras support, for example:

```bash
pipx install "helloagi[telegram]"
pipx install "helloagi[discord]"
```

## Option C: Install from Source

```bash
git clone https://github.com/mmsk2007/helloagi.git
cd helloagi
./scripts/install.sh --source local
```

Or on Windows:

```powershell
git clone https://github.com/mmsk2007/helloagi.git
cd helloagi
.\scripts\install.ps1 -Source local
```

## Option D: Git Install Without Cloning

```bash
curl -fsSL https://raw.githubusercontent.com/mmsk2007/helloagi/main/scripts/install.sh | bash -s -- --source git --ref main
```

This installs from the GitHub repo directly instead of PyPI.

## Option E: Docker

```bash
docker pull ghcr.io/mmsk2007/helloagi:latest
docker run --rm -p 8787:8787 -e ANTHROPIC_API_KEY=your-key ghcr.io/mmsk2007/helloagi:latest
```

Or build from source:

```bash
git clone https://github.com/mmsk2007/helloagi.git
cd helloagi
docker build -t helloagi:latest .
docker run --rm -p 8787:8787 -e ANTHROPIC_API_KEY=your-key helloagi:latest
```

The container runs the HTTP API server on port 8787 by default.

---

## Telegram or Discord after onboarding

1. Install the Telegram extra: `pip install "helloagi[rich,telegram]"` (or `pip install -e ".[rich,telegram]"` from a clone).
2. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token into onboarding or into `.env` as `TELEGRAM_BOT_TOKEN`.
3. Set `ANTHROPIC_API_KEY` in `.env` for Claude-backed replies (unless you use another configured provider).
4. From the directory that contains `.env` and `helloagi.json`, run:

   ```bash
   helloagi serve --telegram
   ```

5. In Telegram, open the bot, send `/start`, then chat normally.

Optional: `helloagi service install --telegram` then `helloagi service start` to run detached (same working directory so `.env` is found).

For Discord:

1. Install the Discord extra: `pip install "helloagi[discord]"`.
2. Put `DISCORD_BOT_TOKEN=...` in `.env` or enter it during onboarding.
3. Start it with `helloagi serve --discord` or `helloagi service install --discord`.

---

## Post-Install Setup

### 1. Run the onboarding wizard

```bash
helloagi onboard
```

The interactive wizard now does the full runtime setup:

- agent identity and focus
- runtime mode (`cli`, `hybrid`, or `service`)
- active provider selection (`template`, `anthropic`, or `google`)
- provider auth mode (`api_key` or `auth_token`)
- auth profile creation for the active provider
- optional OpenAI credential storage for future adapters/tools
- Telegram and Discord channel enablement
- local service auth token (`HELLOAGI_API_KEY`)
- optional migration import from OpenClaw or Hermes

Non-secret onboarding state is saved to `helloagi.onboard.json`; secrets are written to local `.env`.

For scripted installs, you can run onboarding non-interactively:

```bash
helloagi onboard --non-interactive \
  --provider anthropic \
  --auth-mode auth_token \
  --runtime-mode service \
  --enable-extension telegram \
  --agent-name Lana \
  --owner-name You
```

**CLI flags vs OpenAI:** `--provider` accepts only `template`, `anthropic`, or `google`. There is no `--provider openai`. Configure OpenAI with `OPENAI_API_KEY` or `OPENAI_AUTH_TOKEN` in `.env`, or use the interactive wizard’s optional OpenAI credential step.

**PATH tip:** If `helloagi` is not on your PATH yet, use the same interpreter you installed into:

```bash
python -m agi_runtime.cli onboard --help
python -m agi_runtime.cli onboard --non-interactive --provider google --auth-mode api_key --runtime-mode cli
```

(Requires `GOOGLE_API_KEY` in the environment for that example.)

### 2. Initialize runtime config

```bash
helloagi init
```

Creates `helloagi.json` with default mission, style, domain, and file paths.

### 3. Set up API keys (optional)

```bash
cp .env.example .env
# Edit .env:
#   ANTHROPIC_API_KEY=sk-ant-...      or ANTHROPIC_AUTH_TOKEN=...
#   OPENAI_API_KEY=sk-...             or OPENAI_AUTH_TOKEN=...   (optional)
#   GOOGLE_API_KEY=...                or GOOGLE_AUTH_TOKEN=...   (optional)
#   TELEGRAM_BOT_TOKEN=...            (optional)
#   DISCORD_BOT_TOKEN=...             (optional)
#   HELLOAGI_API_KEY=...              (service/dashboard auth)
source .env
```

### 4. Verify the installation

```bash
helloagi doctor
helloagi health
helloagi doctor-score
helloagi auth doctor
helloagi update
```

### 5. Initialize the state database (optional)

```bash
helloagi db-init
```

---

## First Session

```bash
# Interactive mode
helloagi run --goal "Build useful intelligence that teaches and creates value"

# Single question
helloagi oneshot --message "help me plan a launch"

# Autonomous multi-step
helloagi auto --goal "ship v1" --steps 5

# Plan/Execute/Verify loop
helloagi tri-loop --goal "build a growth engine"

# Claude Agent SDK mode
helloagi openclaw --prompt "Help me architect a microservice"

# Local background service
helloagi service install --telegram
helloagi service start
helloagi service status

# Extensions and channels
helloagi extensions list
helloagi extensions doctor
helloagi extensions enable telegram

# Migration preview/apply
helloagi migrate --source openclaw
helloagi migrate --source openclaw --apply --rename-imports
helloagi migrate --source hermes --apply

# Workflow runs
helloagi runs list
helloagi runs show <run-id>
```

---

## Verify HTTP API

```bash
# Start the server
helloagi serve --host 127.0.0.1 --port 8787

# In another terminal:
curl -s http://127.0.0.1:8787/health
curl -s http://127.0.0.1:8787/chat \
  -H 'content-type: application/json' \
  -d '{"message": "help me build an agent"}'
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| **`pip install -e` says “requires 1 argument”** | Pass the project directory: `pip install -e .` (note the dot). |
| **Windows `WinError 183` … `~yping_extensions…dist-info`** | Do not install into a broken conda `base`. Create a **venv** (Option 0), activate it, install again. If you must repair `base`, close all Python processes, delete stray `~*` folders under `Lib\site-packages` that pip left behind, then retry. |
| **`python -m agi_runtime.cli` fails with “No module named agi_runtime”** | Install the package into the **same** Python you are invoking: `pip install -e ".[rich,telegram]"` or `pip install "helloagi[rich,telegram]"`. |
| `command not found: helloagi` | Run `python -m agi_runtime.cli run`, then add Python's user scripts directory to PATH |
| `ModuleNotFoundError: anthropic` | Run `pip install anthropic` |
| Agent returns template responses | Re-run `helloagi onboard` and choose Anthropic or Google, or set `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` |
| Doctor shows missing files | Run `helloagi init` first |
| Service is installed but not reachable | Run `helloagi service status` then `helloagi health` |
| Channel will not start | Run `helloagi extensions doctor` and verify missing env or missing extras |
| Want to import another agent setup | Run `helloagi migrate --source openclaw` or `helloagi migrate --source hermes` |
| Imported files collide with existing state | Re-run migration with `--rename-imports` or `--overwrite` |
| Port 8787 in use | Use `--port 8788` or stop the other process |
| Need to remove the package safely | Run `helloagi uninstall --yes` |

---

## Uninstall

```bash
# If installed with pip
python -m pip uninstall helloagi

# Clean up generated files
rm -f helloagi.json helloagi.onboard.json
rm -rf memory/
```

See also: [Updating](updating.md) and [Uninstall](uninstall.md)
